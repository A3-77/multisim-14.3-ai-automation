# -*- coding: utf-8 -*-
"""MCP 会话层：把 Circuit IR 变成"有状态的电路编辑会话"。

这一层是 P1 的主体，不是 MCP 的薄包装
--------------------------------------
MCP 协议层（`mcp_server.py`）只负责 JSON-RPC 收发。真正的业务逻辑全在这里：

    * 电路句柄（circuit_id）的创建 / 持久化 / 恢复
    * 元件语义参数（amplitude / frequency / resistance）-> IR params 的映射
    * refdes / 探针名的唯一性、自动编号
    * 网络自动命名与合并（含"一个引脚不能属于两条网络"）
    * 自动布局（Agent 永远不需要给坐标）
    * 分析类型与源类型的匹配检查
    * 结构化错误（code / message / hint / context），供 Agent 自纠

为什么坐标由这里决定
--------------------
`add_component` / `connect` 只接受电路语义。坐标是 Multisim 的渲染细节，
由 `layout.plan_ir()` 在 `simulate()` 时按拓扑算出来再写进 IR。

**拓扑判断先于坐标布局**（v0.7.0 起）：`layout.analyze()` 先判断这是什么
拓扑（单主干 + 到地并联支路的哪一类模板），判断不了就明确拒绝；只有判断
成立之后才由 `layout.plan()` 生成坐标。拓扑不是"排不出来"，而是"这类还没
验过"——两者的错误信息必须不同。

v0.7.0 支持的拓扑（详见 tools/layout.py 文件头）：
`shunt_load` / `series_chain` / `divider` / `bypass` / `tee` / `ladder`。
明确拒绝：真正的并联支路（fork）、并联到地（parallel_shunt）、
跨级连接（cross_link）、悬空元件（island）、环路、多电源。

依赖分层
--------
    circuit_session  ->  circuit_ir, ir_compile        （纯 Python，无 COM）
                     ->  ir_sim                         （只在 simulate 时延迟导入）

所以 create/add/connect/add_probe/measure 的纯逻辑部分可以在 64 位 Python 下
跑单元测试，只有 simulate 需要 32 位。

用法
----
    import circuit_session as S
    c = S.create_circuit("rc_lowpass")
    S.add_component(c["circuit_id"], "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE",
                    "V1", value=1.0, frequency=1000.0)
    ...
    r = S.simulate(c["circuit_id"], analysis="transient")
    S.measure(r["sim_id"])
"""
import csv
import json
import math
import os
import re
import shutil
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import circuit_ir as irmod      # noqa: E402
import ir_compile               # noqa: E402
import layout as layoutmod      # noqa: E402

SESS_ROOT = os.path.join(ROOT, "out", "mcp", "sessions")

MAX_PROBES = 9          # LocalName 序号超过一位数字的命名规则未验证
_CID_RE = re.compile(r"^c-[0-9a-f]{10}$")

# ---------------------------------------------------------------------------
# 元件语义参数表
#
# 键是 IR 的 (family, part)，值是**给 Agent 看的**参数名 —— 不是 Multisim 的
# 参数序号。`param` 字段才是落到 IR.params 里的键，只有本模块知道。
# ---------------------------------------------------------------------------
PART_META = {
    ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"): {
        "pins": ("1", "2"), "aliases": {"+": "1", "-": "2"},
        "prefix": "V",
        "value": {"name": "amplitude", "unit": "V", "required": True},
        "extra": {"frequency": {"param": 5, "unit": "Hz", "required": True}},
        "analyses": ("transient",),
    },
    ("POWER_SOURCES", "DC_POWER"): {
        "pins": ("1", "2"), "aliases": {"+": "1", "-": "2"},
        "prefix": "V",
        "value": {"name": "voltage", "unit": "V", "required": True},
        "extra": {},
        "analyses": ("dc", "transient"),
    },
    ("RESISTOR", "RESISTOR_VIRTUAL"): {
        "pins": ("1", "2"), "aliases": {},
        "prefix": "R",
        "value": {"name": "resistance", "unit": "ohm", "required": True},
        "extra": {},
        "analyses": None,          # 无源元件不参与分析类型判定
    },
    ("CAPACITOR", "CAPACITOR_VIRTUAL"): {
        "pins": ("1", "2"), "aliases": {},
        "prefix": "C",
        "value": {"name": "capacitance", "unit": "F", "required": True},
        "extra": {},
        "analyses": None,
    },
    ("POWER_SOURCES", "GROUND"): {
        "pins": ("1",), "aliases": {},
        "prefix": "GND",
        "value": None,             # 地不需要值
        "extra": {},
        "analyses": None,
    },
}


# ---------------------------------------------------------------------------
# 结构化错误
# ---------------------------------------------------------------------------
class SessionError(Exception):
    """所有对外错误都长这样：Agent 拿到后能自己决定下一步怎么改。"""

    def __init__(self, code, message, hint=None, context=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.hint = hint
        self.context = context or {}

    def to_dict(self):
        d = {"code": self.code, "message": self.message}
        if self.hint:
            d["hint"] = self.hint
        if self.context:
            d["context"] = self.context
        return d


def _err(code, message, hint=None, **context):
    return SessionError(code, message, hint, context)


# ---------------------------------------------------------------------------
# 磁盘布局
# ---------------------------------------------------------------------------
def _sess_dir(cid):
    if not _CID_RE.match(str(cid or "")):
        raise _err("BAD_CIRCUIT_ID", "circuit_id 格式不对：%r" % (cid,),
                   "用 create_circuit 返回的 circuit_id，不要自己拼。")
    return os.path.join(SESS_ROOT, cid)


def _ir_path(cid):
    return os.path.join(_sess_dir(cid), "circuit.ir.json")


def _meta_path(cid):
    return os.path.join(_sess_dir(cid), "session.json")


def _sim_dir(cid):
    return os.path.join(_sess_dir(cid), "sims")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _new_id(prefix):
    return "%s-%s" % (prefix, uuid.uuid4().hex[:10])


def _load(cid):
    d = _sess_dir(cid)
    if not os.path.isdir(d):
        raise _err("CIRCUIT_NOT_FOUND", "找不到电路会话 %r" % cid,
                   "先用 create_circuit 建一个。", circuit_id=cid)
    ir = irmod.CircuitIR.load(_ir_path(cid))
    with open(_meta_path(cid), encoding="utf-8") as f:
        meta = json.load(f)
    return ir, meta


def _save(cid, ir, meta):
    d = _sess_dir(cid)
    os.makedirs(d, exist_ok=True)
    meta["updated"] = _now()
    ir.save(_ir_path(cid))
    with open(_meta_path(cid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _part_meta(family, part):
    m = PART_META.get((family, part))
    if m is None:
        raise _err(
            "UNKNOWN_COMPONENT_TYPE",
            "元件类型 %s/%s 不在已验证白名单里" % (family, part),
            "第一版只开放这些：%s" % ", ".join("%s/%s" % k for k in PART_META),
            family=family, part=part,
            supported=["%s/%s" % k for k in PART_META])
    return m


def _norm_pin(comp, pin):
    """IR 层引脚名 -> 实际引脚名；不认识返回 None。"""
    spec = irmod.SUPPORTED.get((comp.family, comp.part))
    if spec is None:
        return None
    pin = str(pin)
    if pin in spec["pins"]:
        return pin
    return (spec.get("aliases") or {}).get(pin)


def _pin_available(comp):
    """可接受的引脚写法（实际引脚 + 别名）。**永远是 list[str]**。"""
    m = PART_META.get((comp.family, comp.part)) or {}
    out = list(m.get("pins") or ())
    for a in (m.get("aliases") or {}):
        if a not in out:
            out.append(a)
    return out


def _real_pins(comp):
    """只有实际引脚名（不含别名）。"""
    m = PART_META.get((comp.family, comp.part)) or {}
    return list(m.get("pins") or ())


def _pin_aliases(comp):
    m = PART_META.get((comp.family, comp.part)) or {}
    return dict(m.get("aliases") or {})


def _pin_hint(comp):
    """给人/给 Agent 看的一句话：可用引脚 1, 2（别名 + -> 1, - -> 2）"""
    avail = _pin_available(comp)
    al = _pin_aliases(comp)
    s = ", ".join(avail)
    if al:
        s += "（别名 " + ", ".join("%s -> %s" % kv for kv in al.items()) + "）"
    return s


def _comp_dict(comp):
    """元件对象 —— 所有工具返回的 `component` / `components[]` 都是这个形状。

    字段**固定**，不会因为元件类型少字段（没有的值是 None / {} / []）。
    - `value` 的语义放在 `value_name` / `value_unit` 里（amplitude / resistance …）
    - `parameters` 永远存在，键是语义名（frequency），**绝不是 Multisim 参数序号**
    """
    m = PART_META.get((comp.family, comp.part)) or {}
    vmeta = m.get("value") or {}
    sem = {}
    for name, spec in (m.get("extra") or {}).items():
        if comp.params and spec["param"] in comp.params:
            sem[name] = comp.params[spec["param"]]
    return {
        "refdes": comp.refdes,
        "family": comp.family,
        "part": comp.part,
        "value": comp.value,
        "value_name": vmeta.get("name"),
        "value_unit": vmeta.get("unit"),
        "parameters": sem,
        "pins": list(m.get("pins") or ()),
        "aliases": dict(m.get("aliases") or {}),
    }


# ---------------------------------------------------------------------------
# 通道（探针 + 它的 Multisim 输出名）
#
# 这是 v0.6.2 的核心修整：Agent 只需要记一个 ID —— probe_id（"P1"）。
# Multisim 那边叫什么（label="探针1"、output="V(探针1)"）是只读的旁证，
# measure / get_waveform 的入参和出参**都只认 probe_id**。
# ---------------------------------------------------------------------------
_PROBE_OUT_RE = re.compile(r"^V\((.+)\)$")


def _label_of(output):
    """COM 输出名 -> Multisim 里显示的探针名。'V(探针1)' -> '探针1'"""
    if not output:
        return None
    m = _PROBE_OUT_RE.match(str(output))
    return m.group(1) if m else str(output)


def _channel(probe_id, net, kind="V", output=None):
    """通道对象 —— `probes[]` 和 `channels{}` 里永远是这一个形状。

    probe_id : 唯一语义 ID，Agent 传参用它
    label    : Multisim 显示的探针名（simulate 之前是 None）
    output   : COM 输出名（simulate 之前是 None）
    """
    return {"probe_id": probe_id, "label": _label_of(output),
            "output": output, "net": net, "kind": kind}


def _rec_probe(p):
    """读仿真记录里的探针条目，兼容 v0.6.0/v0.6.1 写的 `name` 键。"""
    return (p.get("probe_id") or p.get("name"), p.get("net"), p.get("output"))



def _net_of_pin(ir, refdes, pin):
    for n in ir.nets:
        for r, p in n.refs():
            if r == refdes and p == pin:
                return n.name
    return None


def _find_source(ir):
    for c in ir.components:
        if c.part == "GROUND":
            continue
        if c.family in ("POWER_SOURCES", "SIGNAL_VOLTAGE_SOURCES"):
            return c
    return None


def _find_ground(ir):
    gs = [c for c in ir.components if c.part == "GROUND"]
    if not gs:
        return None
    if len(gs) > 1:
        raise _err("MULTIPLE_GROUND", "电路里有 %d 个 GROUND" % len(gs),
                   "第一版只支持一个接地元件（位号 %s）。"
                   % ", ".join(g.refdes for g in gs))
    return gs[0]


def _latest_outputs(cid, meta):
    """从最近一次仿真记录里取 probe_id -> output。

    `get_circuit` 在仿真过之后应该能告诉 Agent "这些探针在 Multisim 里叫什么"，
    而不是永远返回 null。读一个小 JSON，代价可以忽略。
    """
    sims = meta.get("sims") or []
    if not sims:
        return {}
    p = os.path.join(_sim_dir(cid), "%s.json" % sims[-1].get("sim_id"))
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            rec = json.load(f)
    except Exception:
        return {}
    out = {}
    for item in rec.get("probes") or []:
        pid, _net, o = _rec_probe(item)
        if pid:
            out[pid] = o
    return out


def _missing_wiring(ir):
    """列出"元件的引脚还没接到任何网络"的情况。

    只做结构检查，不看仿真参数 —— `ir.validate()` 里那条
    "simulation.stop 必须大于 0" 对"还没仿真过"的电路是噪音，
    放在这里会把每个新电路都判成"没接完"。
    """
    out = []
    for c in ir.components:
        for p in _real_pins(c):
            if _net_of_pin(ir, c.refdes, p) is None:
                out.append("%s.%s 还没接线" % (c.refdes, p))
    return out


def _topology_brief(ir):
    """给状态快照用的拓扑摘要。**永不抛错** —— 电路还没搭完是正常状态。

    `simulate` 用的是严格版本（`plan_layout(..., want_topology=True)`）：
    拓扑不成立就拒绝仿真。这里只回答"我现在搭成什么样了"，所以拓扑不成立
    时把原因一起返回，让 Agent 知道还差什么。

    v0.8.0 起 `supported` 和 `complete` 是两个**互相独立**的判断：

        supported  这种拓扑布局引擎认不认（不认时 reason 说明是哪一类）
        complete   线接完了没有（没接完时 issues 点名哪个引脚）

    分开的理由来自 v0.8.0 验收：`LAYOUT_UNSUPPORTED` 有两种完全不同的含义 ——
    "电路本身没问题，是后端不会摆"（complete=true）和"你还有引脚悬空"
    （complete=false）。以前只有 supported 一个字段，Agent 分不清该改电路
    还是该换拓扑。
    """
    try:
        t = layoutmod.analyze(ir)
    except layoutmod.LayoutError as e:
        d = {"kind": None, "supported": False,
             "reason": e.context.get("reason") or e.code,
             "message": e.message, "hint": e.hint}
    else:
        d = t.to_dict()
        d["supported"] = True

    missing = _missing_wiring(ir)
    has_src = _find_source(ir) is not None
    has_gnd = any(c.part == "GROUND" for c in ir.components)
    # complete 只看"电路本身是否搭完"，**不看布局认不认**：
    # parallel_shunt 那种"接完了但后端不会摆"的情况，complete 必须是 true，
    # 否则 Agent 又会把能力边界当成自己接错线。
    d["complete"] = bool(not missing and ir.probes and has_src and has_gnd)
    if missing:
        d["issues"] = missing[:5]
    elif not ir.probes:
        d["issues"] = ["还没有探针（simulate 需要至少一个）"]
    elif not has_src:
        d["issues"] = ["还没有电源"]
    elif not has_gnd:
        d["issues"] = ["还没有 GROUND"]
    return d


def _describe(cid, ir, meta):
    """统一的状态快照 —— create / add / connect / add_probe / get_circuit 都返回这个形状。"""
    outs = _latest_outputs(cid, meta)
    return {
        "circuit_id": cid,
        "name": ir.name,
        "components": [_comp_dict(c) for c in ir.components],
        "nets": [{"name": n.name, "pins": list(n.pins)} for n in ir.nets],
        "probes": [_channel(p.refdes, p.net, p.kind, outs.get(p.refdes))
                   for p in ir.probes],
        "topology": _topology_brief(ir),
        "simulation": {
            "analysis": ir.simulation.analysis,
            "start": ir.simulation.start,
            "stop": ir.simulation.stop,
            "sample_rate": ir.simulation.sample_rate,
        },
        "simulations": meta.get("sims") or [],
        "counts": {"components": len(ir.components), "nets": len(ir.nets),
                   "probes": len(ir.probes)},
        "warnings": ir.warnings(),
    }


# ---------------------------------------------------------------------------
# 自动命名
# ---------------------------------------------------------------------------
def _auto_refdes(ir, family, part):
    prefix = (PART_META.get((family, part)) or {}).get("prefix") or "X"
    used = {c.refdes for c in ir.components}
    i = 1
    while True:
        cand = "%s%d" % (prefix, i)
        if cand not in used:
            return cand
        i += 1


def _auto_probe_name(ir):
    used = {p.refdes for p in ir.probes} | {c.refdes for c in ir.components}
    i = 1
    while True:
        cand = "P%d" % i
        if cand not in used:
            return cand
        i += 1


def _auto_net_name(ir, pins):
    """含地 -> '0'；含电源正极 -> 'in'；否则 n1/n2/...

    命名只影响可读性，`measure` 是按拓扑算的，不依赖网络名。
    但 '0' 和 'in' 保持与 Circuit IR 约定一致，读起来更自然。

    已经存在同名网络时**不复用**（否则会把不相干的引脚并进去），
    直接退到 n 编号。
    """
    used = {n.name for n in ir.nets}
    has_gnd = any((ir.component(ref) is not None
                   and ir.component(ref).part == "GROUND")
                  for ref, _pin in pins)
    if has_gnd and "0" not in used:
        return "0"
    src = _find_source(ir)
    if src is not None and "in" not in used:
        m = PART_META.get((src.family, src.part)) or {}
        for ref, pin in pins:
            if ref == src.refdes and (m.get("aliases") or {}).get(pin, pin) == "1":
                return "in"
    i = 1
    while "n%d" % i in used:
        i += 1
    return "n%d" % i


# ---------------------------------------------------------------------------
# 布局：委托给 layout.py（拓扑判断先于坐标布局）
#
# 这一层只做一件事：把 layout.LayoutError 转成对外的 SessionError。
# 拓扑分析 / 模板匹配 / 坐标生成全在 layout.py —— 那里不认识 MCP，也不认识
# 会话层，所以可以用纯逻辑单测（tools/test_layout.py）。
# ---------------------------------------------------------------------------
def topology_of(ir):
    """只做拓扑分析，不算坐标。返回 layout.Topology。"""
    try:
        return layoutmod.analyze(ir)
    except layoutmod.LayoutError as e:
        raise SessionError(e.code, e.message, e.hint, e.context)


def plan_layout(ir, want_topology=False):
    """返回 {refdes: [x, y]}；want_topology=True 时返回 (Topology, pos)。

    拓扑不在支持范围内时抛 LAYOUT_UNSUPPORTED，**不猜坐标**。
    """
    try:
        topo, pos = layoutmod.plan_ir(ir)
    except layoutmod.LayoutError as e:
        raise SessionError(e.code, e.message, e.hint, e.context)
    return (topo, pos) if want_topology else pos


# ---------------------------------------------------------------------------
# 工具 1：create_circuit
# ---------------------------------------------------------------------------
def create_circuit(name=None):
    cid = _new_id("c")
    os.makedirs(_sim_dir(cid), exist_ok=True)
    ir = irmod.CircuitIR(name=str(name or cid))
    meta = {"id": cid, "name": ir.name, "created": _now(), "updated": _now(),
            "sims": []}
    _save(cid, ir, meta)
    return _describe(cid, ir, meta)


# ---------------------------------------------------------------------------
# 工具 2：add_component
# ---------------------------------------------------------------------------
def add_component(circuit_id, family, part, refdes=None, value=None,
                  parameters=None, frequency=None, params=None):
    """加一个元件。

    parameters : dict，键是**语义名**（frequency），不是 Multisim 参数序号
    frequency  : 单参数便捷写法，等价于 parameters={"frequency": ...}
    params     : 已废弃，传了会返回 UNSUPPORTED_PARAMETER（绝不静默接受）
    """
    ir, meta = _load(circuit_id)
    m = _part_meta(family, part)

    refdes = (str(refdes).strip() if refdes else "") or _auto_refdes(ir, family, part)
    if ir.component(refdes) is not None:
        raise _err("DUPLICATE_REFDES", "位号 %r 已经存在" % refdes,
                   "换一个位号，或者不传 refdes 让我自动编号。",
                   refdes=refdes,
                   existing=[c.refdes for c in ir.components])
    if any(p.refdes == refdes for p in ir.probes):
        raise _err("DUPLICATE_REFDES", "位号 %r 与已有探针重名" % refdes,
                   refdes=refdes)

    # ---------- value ----------
    vmeta = m.get("value")
    if vmeta is None:
        if value not in (None, 0):
            raise _err("BAD_ARGUMENT", "%s 不接受 value" % part,
                       "%s 没有可设的值，直接不传。" % part,
                       part=part, field="value")
        value = None
    else:
        if value is None:
            if vmeta.get("required"):
                raise _err("MISSING_VALUE",
                           "%s 需要 %s（单位 %s）"
                           % (part, vmeta["name"], vmeta["unit"]),
                           "add_component 里传 value=<数值>（这里是 %s）。"
                           % vmeta["name"],
                           part=part, field="value")
            value = None
        else:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise _err("BAD_ARGUMENT",
                           "value 必须是数字，拿到 %r" % (value,),
                           "value 是 %s（单位 %s）。" % (vmeta["name"],
                                                        vmeta["unit"]),
                           field="value", value=value)
            if value <= 0:
                raise _err("BAD_ARGUMENT",
                           "value 必须大于 0（拿到 %g）" % value,
                           field="value", value=value)

    # ---------- 语义参数 -> IR params ----------
    # 入参只认语义名（frequency）。Multisim 的参数序号（5）永远不出现。
    if params:
        raise _err(
            "UNSUPPORTED_PARAMETER",
            "不接受 params（底层参数序号）",
            "用语义名：add_component(..., parameters={'frequency': 1000})，"
            "或者直接传 frequency=1000。可用参数见该元件的 supported_parameters。",
            field="params",
            supported=list((m.get("extra") or {}).keys()))
    if parameters is not None and frequency is not None:
        raise _err(
            "BAD_ARGUMENT",
            "parameters 和 frequency 同时给了，不知道以哪个为准",
            "只保留一种写法：推荐 parameters={'frequency': 1000}。",
            field="frequency")
    if frequency is not None:
        parameters = dict(parameters or {}, frequency=frequency)
    parameters = dict(parameters or {})

    known = (m.get("extra") or {})
    unknown = [k for k in parameters if k not in known]
    if unknown:
        raise _err(
            "UNKNOWN_PARAMETER",
            "%s 没有参数 %s" % (part, ", ".join(repr(k) for k in unknown)),
            "可用的语义参数：%s" % (", ".join(known) or "（没有）"),
            part=part, field=unknown[0],
            supported=list(known))

    ir_params = {}
    for pname, pspec in known.items():
        got = parameters.get(pname)
        if got is None:
            if pspec.get("required"):
                raise _err("MISSING_PARAMETER",
                           "%s 需要 %s（单位 %s）" % (part, pname, pspec["unit"]),
                           "add_component 里传 parameters={%r: <数值>}。"
                           % pname,
                           part=part, field=pname, supported=list(known))
            continue
        try:
            got = float(got)
        except (TypeError, ValueError):
            raise _err("BAD_ARGUMENT", "%s 必须是数字，拿到 %r" % (pname, got),
                       field=pname, value=got)
        if got <= 0:
            raise _err("BAD_ARGUMENT", "%s 必须大于 0（拿到 %g）" % (pname, got),
                       field=pname, value=got)
        ir_params[pspec["param"]] = got

    comp = irmod.Component(refdes=refdes, family=family, part=part,
                           value=value, params=ir_params, position=None)
    ir.components.append(comp)
    _save(circuit_id, ir, meta)

    out = _describe(circuit_id, ir, meta)
    out["component"] = _comp_dict(comp)
    return out


# ---------------------------------------------------------------------------
# 工具 3：connect
# ---------------------------------------------------------------------------
def _norm_pin_arg(ir, item):
    """接受 ("V1", "+") / ["V1", "+"] / "V1.+"。返回 (refdes, pin)。"""
    if isinstance(item, str):
        ref, dot, pin = item.partition(".")
        if not dot or not ref or not pin:
            raise _err("BAD_ARGUMENT", "引脚写法不对：%r" % item,
                       "用 'V1.+' 或 ['V1', '+'] 这种写法。")
        return ref, pin
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return str(item[0]), str(item[1])
    raise _err("BAD_ARGUMENT", "引脚写法不对：%r" % (item,),
               "用 'V1.+' 或 ['V1', '+'] 这种写法。")


def connect(circuit_id, pins, net=None):
    ir, meta = _load(circuit_id)
    if not isinstance(pins, (list, tuple)) or len(pins) < 1:
        raise _err("BAD_ARGUMENT", "pins 必须是非空数组",
                   "例：connect(pins=[['V1','+'],['R1','1']], net='in')")

    resolved = []
    for item in pins:
        ref, pin = _norm_pin_arg(ir, item)
        comp = ir.component(ref)
        if comp is None:
            raise _err("COMPONENT_NOT_FOUND", "元件 %r 不存在" % ref,
                       "先 add_component 再 connect。",
                       refdes=ref, existing=[c.refdes for c in ir.components])
        real = _norm_pin(comp, pin)
        if real is None:
            raise _err("PIN_NOT_FOUND",
                       "%s（%s/%s）没有引脚 %r"
                       % (ref, comp.family, comp.part, pin),
                       "可用引脚：%s" % _pin_hint(comp),
                       refdes=ref, pin=pin,
                       available=_pin_available(comp),
                       aliases=_pin_aliases(comp))
        resolved.append((ref, real))

    # ---------- 决定网络名 ----------
    # 规则（都是为了让 Agent 能"逐条描述连线"而不必一次给全）：
    #   * 显式给了 net：这些引脚不能已经属于别的网络
    #   * 没给 net，但引脚全在同一个已有网络里：复用那个网络（幂等追加）
    #   * 没给 net，引脚分属不同网络：报错，不能靠猜合并
    #   * 没给 net，全是新引脚：自动命名
    owners = [_net_of_pin(ir, ref, pin) for ref, pin in resolved]
    name = (str(net).strip() if net else "")

    if name:
        for (ref, pin), owner in zip(resolved, owners):
            if owner is not None and owner != name:
                raise _err("PIN_ALREADY_CONNECTED",
                           "引脚 %s.%s 已经属于网络 %r，不能再连到 %r"
                           % (ref, pin, owner, name),
                           "同一个引脚只能属于一条网络；要改连接先重建电路。",
                           refdes=ref, pin=pin, net=name, existing=[owner])
    else:
        distinct = {o for o in owners if o is not None}
        if len(distinct) > 1:
            raise _err("PIN_ALREADY_CONNECTED",
                       "这些引脚分属不同网络（%s），不能直接并到一起"
                       % ", ".join(sorted(distinct)),
                       "同一个引脚只能属于一条网络；要么显式给 net= 指定目标网络，"
                       "要么分两次 connect。",
                       net=None, existing=sorted(distinct),
                       pins=["%s.%s" % p for p in resolved])
        if len(distinct) == 1:
            name = next(iter(distinct))
        else:
            name = _auto_net_name(ir, resolved)

    existing = ir.net(name)
    created = existing is None
    if created:
        if len(resolved) < 2:
            raise _err("BAD_ARGUMENT",
                       "新建网络 %r 只有 %d 个引脚，至少要 2 个" % (name, len(resolved)),
                       "给 pins 至少两个引脚，或把它接到已存在的网络上。",
                       net=name, pins=["%s.%s" % p for p in resolved])
        ir.nets.append(irmod.Net(name=name, pins=["%s.%s" % p for p in resolved]))
    else:
        for ref, pin in resolved:
            tok = "%s.%s" % (ref, pin)
            if tok not in existing.pins:
                existing.pins.append(tok)

    _save(circuit_id, ir, meta)
    out = _describe(circuit_id, ir, meta)
    # `net` 的形状与 _describe 里的 nets[] 完全一致（name + pins），
    # "是不是新建的" 放在顶层，不塞进 net 里。
    out["net"] = {"name": name, "pins": list(ir.net(name).pins)}
    out["created"] = created
    return out


# ---------------------------------------------------------------------------
# 工具 4：add_probe
# ---------------------------------------------------------------------------
def _resolve_target(ir, target):
    """target 可以是网络名、'R1.2' 引脚、或 'R1' 元件（两端 -> 报错要求明确）。"""
    t = str(target or "").strip()
    if not t:
        raise _err("BAD_ARGUMENT", "target 不能为空",
                   "传网络名（'out'）或引脚（'R1.2'）。")
    if ir.net(t) is not None:
        return t
    ref, dot, pin = t.partition(".")
    if dot:
        comp = ir.component(ref)
        if comp is None:
            raise _err("COMPONENT_NOT_FOUND", "元件 %r 不存在" % ref, refdes=ref)
        real = _norm_pin(comp, pin)
        if real is None:
            raise _err("PIN_NOT_FOUND",
                       "%s 没有引脚 %r" % (ref, pin),
                       "可用引脚：%s" % _pin_hint(comp),
                       refdes=ref, pin=pin,
                       available=_pin_available(comp),
                       aliases=_pin_aliases(comp))
        net = _net_of_pin(ir, ref, real)
        if net is None:
            raise _err("PIN_NOT_CONNECTED", "引脚 %s.%s 还没接到任何网络" % (ref, real),
                       "先 connect 它。", refdes=ref, pin=real)
        return net
    comp = ir.component(t)
    if comp is not None:
        raise _err("AMBIGUOUS_TARGET",
                   "%r 是一个元件，它有两个引脚，探针该放哪个？" % t,
                   "改用网络名，或写成 '%s.1' / '%s.2'。" % (t, t),
                   refdes=t,
                   available=["%s.%s" % (t, p) for p in _real_pins(comp)],
                   aliases=_pin_aliases(comp))
    raise _err("NET_NOT_FOUND", "找不到网络 %r" % t,
               "可用网络：%s" % [n.name for n in ir.nets],
               target=t, nets=[n.name for n in ir.nets])


def add_probe(circuit_id, target, name=None):
    ir, meta = _load(circuit_id)
    net = _resolve_target(ir, target)

    if len(ir.probes) >= MAX_PROBES:
        raise _err("PROBE_LIMIT",
                   "探针数量已达上限 %d" % MAX_PROBES,
                   "探针名超过一位数字时的命名规则还没验证，"
                   "第一版最多 %d 个探针。" % MAX_PROBES,
                   count=len(ir.probes), limit=MAX_PROBES)

    pname = (str(name).strip() if name else "") or _auto_probe_name(ir)
    if any(p.refdes == pname for p in ir.probes):
        raise _err("PROBE_DUPLICATE", "探针名 %r 重复" % pname,
                   "换一个名字，或不传 name 让我自动编号。",
                   probe_id=pname, existing=[p.refdes for p in ir.probes])
    if ir.component(pname) is not None:
        raise _err("PROBE_DUPLICATE", "探针名 %r 与元件位号重名" % pname,
                   "换一个名字。", probe_id=pname,
                   existing=[c.refdes for c in ir.components])

    pr = irmod.Probe(refdes=pname, kind="V", net=net)
    ir.probes.append(pr)
    _save(circuit_id, ir, meta)
    out = _describe(circuit_id, ir, meta)
    out["probe"] = _channel(pr.refdes, pr.net, pr.kind)
    return out


# ---------------------------------------------------------------------------
# 工具 5：simulate
# ---------------------------------------------------------------------------
_IRSIM = None


def _ir_sim():
    """延迟导入：ir_sim 会 import msc（COM），64 位 Python 下不可用。"""
    global _IRSIM
    if _IRSIM is None:
        import ir_sim as m
        _IRSIM = m
    return _IRSIM


def _check_analysis(ir, analysis):
    src = _find_source(ir)
    if src is None:
        raise _err("NO_SOURCE", "电路里没有电源，无法仿真",
                   "先 add_component 一个 DC_POWER 或 AC_VOLTAGE。")
    m = PART_META.get((src.family, src.part)) or {}
    supported = m.get("analyses")
    if supported is None:
        raise _err("NO_SOURCE", "找不到可以作为激励的电源")
    if analysis not in supported:
        raise _err(
            "ANALYSIS_NOT_SUPPORTED",
            "%s 不支持 %s（当前后端只验证过 %s）"
            % (src.part, analysis, " / ".join(supported)),
            "把 analysis 改成 %r，或者把源换成支持 %r 的类型。"
            % (supported[0], analysis),
            analysis=analysis, source_part=src.part, source_refdes=src.refdes,
            supported=list(supported))
    return src


def _default_analysis(ir):
    src = _find_source(ir)
    if src is None:
        return "transient"
    m = PART_META.get((src.family, src.part)) or {}
    supported = m.get("analyses") or ("transient",)
    return supported[0]


def simulate(circuit_id, analysis=None, start=None, stop=None,
             sample_rate=None, timeout=None):
    """编译 + 真跑 Multisim。

    timeout 是**软超时**：只在阶段之间（布局 / 编译 / 跑仿真）检查，
    无法中断已经在进行的 Multisim COM 调用。超时会返回 SIMULATION_TIMEOUT，
    并带上已完成阶段的耗时 —— 这样 Agent 至少知道"卡在哪一步"。
    真正的硬超时和 progress 通知留给后续版本（见 docs/mcp.md）。
    """
    t_begin = time.time()
    budget = None
    if timeout is not None:
        try:
            budget = float(timeout)
        except (TypeError, ValueError):
            raise _err("BAD_ARGUMENT", "timeout 必须是秒数，拿到 %r" % (timeout,),
                       field="timeout", value=timeout)
        if budget <= 0:
            raise _err("BAD_ARGUMENT", "timeout 必须大于 0（拿到 %g）" % budget,
                       field="timeout", value=budget)

    def _spent():
        return round(time.time() - t_begin, 3)

    def _check(phase):
        if budget is not None and _spent() > budget:
            raise _err("SIMULATION_TIMEOUT",
                       "仿真超过 %.1f s 预算（%s 阶段后已用 %.1f s）"
                       % (budget, phase, _spent()),
                       "调大 timeout；或者缩短 stop / 降低 sample_rate。"
                       "注意这是软超时，无法中断已开始的 Multisim 调用。",
                       phase=phase, elapsed_s=_spent(), timeout_s=budget)

    ir, meta = _load(circuit_id)

    if not ir.probes:
        raise _err("NO_PROBE", "电路里没有探针，仿真出来也读不到数",
                   "先 add_probe 一个网络。")

    analysis = analysis or _default_analysis(ir)
    src = _check_analysis(ir, analysis)

    # ---------- 仿真参数 ----------
    #
    # 先算参数再校验：validate() 会检查 simulation.stop > 0，而 stop 是按源
    # 频率推出来的。顺序反了会把"参数还没算"误报成"电路不完整"。
    s = ir.simulation
    s.analysis = analysis
    if analysis == "dc":
        s.start, s.stop, s.step, s.sample_rate = 0.0, 0.0, None, 0.0
    else:
        if stop is not None:
            s.stop = float(stop)
        elif not s.stop or s.stop <= 0:
            freq = float((src.params or {}).get(5) or 0.0)
            if freq <= 0:
                raise _err("MISSING_PARAMETER",
                           "%s 没有频率，无法推算仿真窗口" % src.refdes,
                           "显式传 stop（秒）和 sample_rate（Hz）。")
            s.stop = 6.0 / freq
        if sample_rate is not None:
            s.sample_rate = float(sample_rate)
        elif not s.sample_rate or s.sample_rate <= 0:
            freq = float((src.params or {}).get(5) or 0.0)
            s.sample_rate = 200.0 * freq if freq > 0 else 200000.0
        if start is not None:
            s.start = float(start)
        if s.start and s.start < 0:
            raise _err("BAD_ARGUMENT", "start 不能是负数（拿到 %g）" % s.start,
                       field="start", value=s.start)
        if s.start and s.stop and s.start >= s.stop:
            raise _err("BAD_ARGUMENT",
                       "start (%g) 必须小于 stop (%g)" % (s.start, s.stop),
                       "start 是导出窗口的起点，stop 是终点。",
                       field="start", value=s.start, stop=s.stop)

    # ---------- 再校验电路完整性 ----------
    #
    # 排在拓扑判断之前：一个"元件没接线"的电路，从拓扑层看是 island，
    # 但 Agent 需要的是"R2 的引脚 2 没接"这种具体信息。校验先跑，错误更准。
    errs = ir.validate()
    if errs:
        raise _err("VALIDATION_FAILED",
                   "电路还不完整，有 %d 项问题" % len(errs),
                   "按 issues 逐条修，修完再 simulate。",
                   issues=errs)

    # ---------- 拓扑 + 布局（先判断拓扑，再算坐标） ----------
    topo, pos = plan_layout(ir, want_topology=True)
    for comp in ir.components:
        comp.position = pos.get(comp.refdes, comp.position)
    t_layout = _spent()
    _check("layout")

    # ---------- 落盘 + 编译 ----------
    _save(circuit_id, ir, meta)

    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", ir.name or circuit_id)
    ms14 = os.path.join(_sess_dir(circuit_id), "%s.ms14" % name)
    try:
        crep = ir_compile.compile_ir(ir, ms14, verbose=False)
    except ir_compile.CompileError as e:
        raise _err("COMPILE_FAILED", "IR -> .ms14 失败：%s" % e,
                   "这通常是布局或引脚映射的问题，检查 issues。")
    t_compile = _spent()
    _check("compile")

    # ---------- 跑仿真 ----------
    isim = _ir_sim()
    if analysis == "dc":
        res = isim.simulate_dc(ms14, verbose=False)
    else:
        res = isim.simulate(ms14, s.stop, s.sample_rate, verbose=False)
    t_run = _spent()
    _check("run")

    # ---------- start 生效（v0.8.0） ----------
    #
    # Multisim 的 COM 接口没有"从 t0 起算"的入口：`run(stop)` 永远从 0 开始。
    # v0.7.0 把 start 收进 IR 就没管了 —— 传了不报错、也不生效，是最容易
    # 误导人的一类静默行为（v0.8.0 验收里 Agent 因此把启动暂态混进了拟合窗）。
    # 现在的做法：仿真照旧从 0 跑，**导出窗口**裁掉 t < start 的采样点。
    # 语义在 schema 里写清楚，不再假装能省掉这段计算。
    if analysis != "dc" and s.start and s.start > 0:
        trimmed = {}
        for nm, (tt, vv) in res["data"].items():
            keep = [(a, b) for a, b in zip(tt, vv) if a >= s.start - 1e-15]
            if keep:
                trimmed[nm] = ([p[0] for p in keep], [p[1] for p in keep])
        if not trimmed:
            raise _err("SIMULATION_FAILED",
                       "start=%g 之后没有任何采样点（仿真只到 %g s）"
                       % (s.start, s.stop),
                       "把 start 调小，或把 stop 调大。",
                       start=s.start, stop=s.stop)
        res["data"] = trimmed

    timing = {"layout_s": round(t_layout, 3),
              "compile_s": round(t_compile - t_layout, 3),
              "run_s": round(t_run - t_compile, 3),
              "total_s": t_run}

    if len(res["data"]) == 0:
        raise _err(
            "SIMULATION_FAILED",
            "Multisim 没有返回任何数据（state=%s）" % res.get("state"),
            "检查探针是否真的落在导线上；不要在没有探针的网络上仿真。",
            state=res.get("state"), outputs=res.get("outputs"))

    # ---------- 落盘 ----------
    sid = _new_id("s")
    sim_dir = _sim_dir(circuit_id)
    os.makedirs(sim_dir, exist_ok=True)

    snap = os.path.join(sim_dir, "%s.ir.json" % sid)
    ir.save(snap)

    outs = list(res["outputs"])
    chans = [nm for nm in outs if nm in res["data"]]
    npts = min(len(res["data"][nm][1]) for nm in chans) if chans else 0
    csv_path = os.path.join(sim_dir, "%s.csv" % sid)
    if chans:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t"] + chans)
            for i in range(npts):
                row = ["%.9g" % res["data"][chans[0]][0][i]]
                for nm in chans:
                    row.append("%.9g" % res["data"][nm][1][i])
                w.writerow(row)

    # 通道对象：probe_id 是唯一 ID，output 只是 Multisim 那边的旁证
    probe_map = []
    for i, pr in enumerate(ir.probes):
        probe_map.append(_channel(pr.refdes, pr.net, pr.kind,
                                  outs[i] if i < len(outs) else None))

    summary = {}
    for ch in probe_map:
        nm = ch["output"]
        if nm not in chans:
            continue
        v = res["data"][nm][1]
        summary[ch["probe_id"]] = {"n": len(v), "min": min(v), "max": max(v),
                                   "mean": sum(v) / len(v)}

    rec = {
        "sim_id": sid, "circuit_id": circuit_id, "analysis": analysis,
        "status": "ok", "created": _now(),
        "outputs": outs, "probes": probe_map,
        "rlc_reported_by_multisim": res.get("rlc") or {},
        "state": res.get("state"), "sample_rate": s.sample_rate,
        "stop": s.stop, "start": s.start, "n": npts,
        "ms14": os.path.relpath(ms14, ROOT),
        "ir_snapshot": os.path.relpath(snap, ROOT),
        "waveform": os.path.relpath(csv_path, ROOT) if chans else None,
        "summary": summary,
        "topology": topo.to_dict(),
        "timing": timing,
        "compile": {"bytes": crep.get("bytes")},
    }
    rec_path = os.path.join(sim_dir, "%s.json" % sid)
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")

    meta.setdefault("sims", []).append(
        {"sim_id": sid, "analysis": analysis, "created": rec["created"],
         "n": npts})
    _save(circuit_id, ir, meta)

    out = dict(rec)
    out["ok"] = True
    out["record"] = os.path.relpath(rec_path, ROOT)
    return out


# ---------------------------------------------------------------------------
# 工具 6：measure
# ---------------------------------------------------------------------------
def _load_sim(sim_id):
    sid = str(sim_id or "")
    if not re.match(r"^s-[0-9a-f]{10}$", sid):
        raise _err("BAD_SIM_ID", "sim_id 格式不对：%r" % (sim_id,),
                   "用 simulate 返回的 sim_id。")
    base = os.path.join(SESS_ROOT)
    for cid in os.listdir(base) if os.path.isdir(base) else []:
        p = os.path.join(base, cid, "sims", "%s.json" % sid)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
            rec["_dir"] = os.path.join(base, cid, "sims")
            return rec
    raise _err("SIM_NOT_FOUND", "找不到仿真 %r" % sim_id,
               "simulate 的结果只在 out/mcp/sessions 下；换一个 sim_id。")


def _read_waveform(rec):
    """返回 (names, t, {name: [v]})。"""
    path = os.path.join(ROOT, rec["waveform"]) if rec.get("waveform") else None
    if not path or not os.path.isfile(path):
        raise _err("SIMULATION_FAILED", "找不到波形文件 %r" % rec.get("waveform"))
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], [], {}
    header = rows[0][1:]
    t, data = [], {nm: [] for nm in header}
    for r in rows[1:]:
        if not r:
            continue
        t.append(float(r[0]))
        for i, nm in enumerate(header, 1):
            data[nm].append(float(r[i]))
    return header, t, data


def _topology(ir):
    """算出 measure 需要的位置信息，不依赖网络叫什么名字。"""
    src = _find_source(ir)
    gnd = _find_ground(ir)
    m = PART_META.get((src.family, src.part)) if src else {}
    pos_pin = ((m or {}).get("aliases") or {}).get("+", "1")
    v_in_net = _net_of_pin(ir, src.refdes, pos_pin) if src else None
    v_gnd_net = _net_of_pin(ir, gnd.refdes, "1") if gnd else None
    rs = [c for c in ir.components if c.family == "RESISTOR"]
    return {"src": src, "gnd": gnd, "v_in_net": v_in_net,
            "v_gnd_net": v_gnd_net, "resistors": rs}


_ID_KEYS = ("probe_id", "label", "output", "net", "kind")


def _probe_not_found(given, rec):
    """探针找不到时，尽量告诉 Agent「你传的是什么、该传什么」。"""
    items = [(_rec_probe(p)) for p in (rec.get("probes") or [])]
    ids = [i[0] for i in items]
    by_output = {i[2]: i[0] for i in items if i[2]}
    by_label = {_label_of(i[2]): i[0] for i in items if i[2]}
    g = str(given or "")
    if g in by_output or g in by_label:
        pid = by_output.get(g) or by_label.get(g)
        return _err("PROBE_NOT_FOUND",
                    "%r 是 Multisim 那边的名字，不是 probe_id" % g,
                    "probe_id 是 %r。measure / get_waveform 只接受 probe_id；"
                    "label / output 是只读旁证，不要拿它传参。" % pid,
                    field="probe_id", value=g, available=ids, matched=pid)
    return _err("PROBE_NOT_FOUND", "没有探针 %r" % given,
                "可用 probe_id：%s" % (", ".join(ids) or "（没有）"),
                field="probe_id", value=g, available=ids)


def _pair_probes(chans, order, topo, ir):
    """选出"输入探针 / 输出探针"。返回 (in_pid, out_pid, pairing)。

    **v0.8.0 修的就是这里。** v0.7.0 直接拿探针的**添加顺序**当输入/输出：
    先加的算输入、后加的算输出。于是"先放输出探针、后放输入探针"的电路
    会得到 gain = 1/真值、相位符号翻转 —— 而返回里 `mode="ratio"` 加上
    `in_probe` / `out_probe` 两个字段看起来非常权威，Agent 不核对就会写错。

    现在优先按**拓扑**配对：
        输入 = 源正极所在的网络（`_topology()` 已经算好）
        输出 = `layout.analyze().out_net`
    两个都找到且不是同一个探针，才用 ratio 模式；否则退回添加顺序，
    并把 `pairing="probe_order"` 写进返回 —— 让 Agent 知道这个 gain 是
    "按顺序猜的"，不是"按拓扑算的"。
    """
    net_in = topo.get("v_in_net")
    out_net = None
    try:
        out_net = layoutmod.analyze(ir).out_net
    except Exception:
        out_net = None

    in_pid = next((pid for pid in order if chans[pid].get("net") == net_in), None)
    out_pid = next((pid for pid in order
                    if out_net is not None and chans[pid].get("net") == out_net),
                   None)
    if in_pid and out_pid and in_pid != out_pid:
        return in_pid, out_pid, "topology"
    if len(order) >= 2:
        return order[0], order[1], "probe_order"
    single = order[0] if order else None
    return single, single, "single"


def measure(sim_id, what="all", probe_id=None):
    rec = _load_sim(sim_id)
    ir = irmod.CircuitIR.load(os.path.join(ROOT, rec["ir_snapshot"]))
    names, t, data = _read_waveform(rec)
    topo = _topology(ir)

    # 通道一律以 probe_id 为键；output 只是旁证字段
    chans = {}
    for item in rec.get("probes") or []:
        pid, net, output = _rec_probe(item)
        if probe_id and pid != probe_id:
            continue
        if output not in data:
            continue
        v = data[output]
        ch = _channel(pid, net, "V", output)
        ch.update({"n": len(v), "min": min(v), "max": max(v),
                   "mean": sum(v) / len(v),
                   "rms": math.sqrt(sum(x * x for x in v) / len(v))})
        chans[pid] = ch

    if not chans:
        raise _probe_not_found(probe_id, rec)

    out = {"ok": True, "sim_id": sim_id, "analysis": rec["analysis"],
           "what": what,
           "probes": [_channel(_rec_probe(p)[0], _rec_probe(p)[1],
                               kind="V", output=_rec_probe(p)[2])
                      for p in (rec.get("probes") or [])],
           "channels": chans, "notes": []}

    if rec["analysis"] == "dc":
        # ---------- 直流：按拓扑算电阻电压 / 电流 ----------
        by_net = {}
        for item in rec.get("probes") or []:
            pid, net, _o = _rec_probe(item)
            if pid in chans:
                by_net[net] = chans[pid]["mean"]
        v_in = by_net.get(topo["v_in_net"]) if topo["v_in_net"] else None
        v_gnd = by_net.get(topo["v_gnd_net"]) if topo["v_gnd_net"] else None
        out.update({"v_source_net": v_in, "v_ground_net": v_gnd})

        r = topo["resistors"][0] if len(topo["resistors"]) == 1 else None
        r_ms = (rec.get("rlc_reported_by_multisim") or {}).get(r.refdes) if r else None
        v_r = None if (v_in is None or v_gnd is None) else v_in - v_gnd
        i_r = None
        if v_r is not None and r is not None:
            r_use = r_ms if r_ms else r.value
            if r_use:
                i_r = v_r / r_use
        out.update({
            "v_resistor": v_r,
            "r": r_ms if r_ms else (r.value if r else None),
            "r_source": "multisim" if r_ms else ("ir" if r else None),
            "current": i_r,
            "current_source": "I = V_R / R（欧姆定律，电压来自探针实测）",
        })
        if v_in is None:
            out["notes"].append(
                "源正极所在网络没有探针，算不出电阻电压 —— 在那个网络上 add_probe。")
        if v_gnd is None:
            out["notes"].append(
                "地网络没有探针，算不出电阻电压 —— 在接地网络上 add_probe。")

        th = _ir_sim().theory_dc(ir)
        out["theory"] = th
    else:
        # ---------- 瞬态：复用 ir_sim 的最小二乘拟合 ----------
        isim = _ir_sim()
        freq = float((topo["src"].params or {}).get(5) or 0.0) if topo["src"] else 0.0
        if freq <= 0:
            raise _err("MISSING_PARAMETER", "源没有频率，无法做正弦拟合",
                       "AC_VOLTAGE 需要 frequency。")
        fits = isim.fit_channels({nm: (t, data[nm])
                                  for nm in data}, freq)
        fit_of = {nm: (a, ph, off) for nm, a, ph, off in fits}
        for pname, ch in chans.items():
            f = fit_of.get(ch["output"])
            if f:
                ch["amp"] = f[0]
                ch["phase_deg"] = math.degrees(f[1])
                ch["offset"] = f[2]

        order = [p["probe_id"] for p in out["probes"] if p["probe_id"] in chans]
        src_amp = float(topo["src"].value or 0.0) if topo["src"] else 0.0

        in_pid, out_pid, pairing = _pair_probes(chans, order, topo, ir)
        out["pairing"] = pairing
        if pairing == "topology":
            a_in = chans[in_pid].get("amp")
            a_out = chans[out_pid].get("amp")
            out["mode"] = "ratio"
            out["in_probe"] = in_pid
            out["out_probe"] = out_pid
            out["gain"] = (a_out / a_in) if (a_in and a_out is not None) else None
            p_in = chans[in_pid].get("phase_deg")
            p_out = chans[out_pid].get("phase_deg")
            if p_in is not None and p_out is not None:
                d = p_out - p_in
                while d > 180:
                    d -= 360
                while d < -180:
                    d += 360
                out["phase_deg"] = d
        else:
            # 只有一个探针（或拓扑判断不出输入/输出网络）：用源声明的幅值当参考
            single = out_pid if out_pid else (order[0] if order else None)
            amp0 = chans[single].get("amp") if single else None
            out["mode"] = "absolute"
            out["out_probe"] = single
            out["gain"] = (amp0 / src_amp) if (amp0 and src_amp) else None
            if single:
                ph = chans[single].get("phase_deg")
                if ph is not None:
                    out["phase_deg"] = ph
            if len(order) >= 2:
                out["notes"].append(
                    "拓扑判断不出输入/输出网络，gain 按探针添加顺序配对"
                    "（pairing=probe_order），可能方向相反；"
                    "更稳的做法是用 channels[].amp 自己算比值。")

        out["source_amp"] = src_amp
        out["source_freq"] = freq
        out["theory"] = isim.theory(ir)

    # ---------- what 过滤 ----------
    keep = {
        "all": None,
        "voltage": ("mean", "rms", "min", "max"),
        "amplitude": ("amp",),
        "phase": ("phase_deg",),
        "dc_voltage": ("mean",),
    }
    if what not in keep:
        raise _err("BAD_ARGUMENT", "what=%r 不支持" % what,
                   "可用：%s" % ", ".join(keep))
    keys = keep[what]
    if keys is not None:
        for pid, ch in chans.items():
            # 身份字段永远保留 —— 否则 what="amplitude" 之后 Agent 就不知道
            # 这个通道是哪个探针了（这正是 v0.6.1 暴露的问题）
            chans[pid] = {k: v for k, v in ch.items()
                          if k in keys or k in _ID_KEYS}
    return out


# ---------------------------------------------------------------------------
# 工具 7：get_waveform
# ---------------------------------------------------------------------------
def get_waveform(sim_id, probe_id=None, max_points=200):
    rec = _load_sim(sim_id)
    names, t, data = _read_waveform(rec)
    if not names:
        raise _err("SIMULATION_FAILED", "波形文件是空的")

    chans_of = {}
    for item in rec.get("probes") or []:
        pid, net, output = _rec_probe(item)
        if output in data:
            chans_of[pid] = (net, output)
    if not chans_of:
        raise _err("SIMULATION_FAILED",
                   "这次仿真没有任何通道有数据",
                   "检查探针是否落在导线上。", outputs=names)

    if probe_id:
        if probe_id not in chans_of:
            raise _probe_not_found(probe_id, rec)
        chans_of = {probe_id: chans_of[probe_id]}

    out = {"ok": True, "sim_id": sim_id, "analysis": rec["analysis"],
           "sample_rate": rec.get("sample_rate"), "n": len(t),
           "t_range": [t[0], t[-1]] if t else [],
           "artifact": rec.get("waveform"),
           "probes": [_channel(_rec_probe(p)[0], _rec_probe(p)[1],
                               kind="V", output=_rec_probe(p)[2])
                      for p in (rec.get("probes") or [])],
           "channels": {}}

    try:
        max_points = int(max_points)
    except (TypeError, ValueError):
        max_points = 200
    max_points = max(2, min(max_points, 5000))

    # v0.8.0：预览改成"在整段窗口上均匀取 max_points 个点（含首尾）"。
    # 旧写法是 range(0, n, n//max_points)：当步长正好等于信号周期的整数倍时
    # （1600 点 / 8 点 = 200 点 = 1 kHz 的整整一个周期），每个预览点落在
    # 同一相位上，画出来是一条水平线 —— v0.8.0 验收里 Agent 据此误判
    # "preview 数据错位"。数据本身没错，是抽样方式会混叠。改成非整数步长后
    # 采样相位逐点移动，不会再出现这种假象。
    n_t = len(t)
    if n_t <= max_points:
        idx = list(range(n_t))
        step = 1
    else:
        idx = sorted({int(round(k * (n_t - 1) / float(max_points - 1)))
                      for k in range(max_points)})
        step = round((n_t - 1) / float(max_points - 1), 3)

    for pid, (net, nm) in chans_of.items():
        v = data[nm]
        ch = _channel(pid, net, "V", nm)
        ch.update({
            "n": len(v), "min": min(v), "max": max(v),
            "mean": sum(v) / len(v),
            "preview": {"t": [t[i] for i in idx],
                        "v": [v[i] for i in idx]},
        })
        out["channels"][pid] = ch
    out["preview_step"] = step
    return out


# ---------------------------------------------------------------------------
# 会话管理（给调试和测试用）
# ---------------------------------------------------------------------------
def list_sessions():
    if not os.path.isdir(SESS_ROOT):
        return []
    out = []
    for cid in sorted(os.listdir(SESS_ROOT)):
        p = os.path.join(SESS_ROOT, cid, "session.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def get_circuit(circuit_id):
    ir, meta = _load(circuit_id)
    return _describe(circuit_id, ir, meta)


def delete_circuit(circuit_id):
    d = _sess_dir(circuit_id)
    if not os.path.isdir(d):
        raise _err("CIRCUIT_NOT_FOUND", "找不到电路会话 %r" % circuit_id)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True, "deleted": circuit_id}
