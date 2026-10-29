# -*- coding: utf-8 -*-
"""Multisim 电路执行器 —— MCP Server（stdio 传输，纯标准库）。

为什么不用第三方 MCP SDK
------------------------
这个仓库的硬约束是"零第三方依赖 + 必须 32 位 Python"（COM 限制）。
MCP 的 stdio 传输就是「一行一个 JSON-RPC 2.0 消息」，实现一个够用的子集
比引入依赖并让它兼容 32 位环境更省事。这里只实现 Agent 真正会用到的三条：
    initialize / tools/list / tools/call

八个工具（都在 circuit_session 里实现，这里只做协议适配）
--------------------------------------------------------
    create_circuit    建会话，拿 circuit_id
    add_component     加元件（value + parameters，语义名，不暴露参数序号）
    connect           连网络（自动命名、自动判重）
    add_probe         加探针（按网络名或引脚，自动唯一命名）
    get_circuit       只读地取回电路当前状态（跨调用/跨会话核对用）
    simulate          transient / dc，自动布局 + 编译 + 跑 Multisim
    measure           增益 / 相位 / 幅值 / 直流电压
    get_waveform      波形摘要 + 预览 + 产物路径

一条贯穿所有工具的约定（v0.6.2）
--------------------------------
**探针只有 probe_id 一个身份。** `P1` 是唯一语义 ID，`measure` / `get_waveform`
的入参和 `channels` 的键都用它。`label`（探针1）/ `output`（V(探针1)）是 Multisim
那边的只读旁证，绝不参与寻址。

stdout 只走协议
---------------
启动时把 sys.stdout 换到 stderr，所有 print（包括 ir_sim 里的）都不会污染
JSON-RPC 流。真正的协议输出走保存下来的 `_PROTO_OUT`。这一条是硬的：
任何一行非 JSON 写到 stdout，客户端立刻解析失败。

跑法（必须 32 位 Python，COM 限制）
-----------------------------------
    runtime\\py32\\python.exe -u tools\\mcp_server.py
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------- stdout 保护
_PROTO_OUT = sys.stdout
try:
    _PROTO_OUT.reconfigure(encoding="utf-8", newline="\n")
except Exception:
    pass
sys.stdout = sys.stderr          # 任何 print 都去 stderr
try:
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

import circuit_session as S     # noqa: E402

SERVER_NAME = "multisim-circuit"
SERVER_VERSION = "0.9.0"
PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# 工具 schema
#
# **这个 schema 就是 Agent 的 API 文档。** 描述写错了，Agent 就会写错代码 ——
# 而且从日志里看不出是 API 的问题还是模型的问题。所以：
#   * 每个参数的 description 必须和实现一致（v0.6.1 的 get_waveform 就是反例）
#   * 返回对象的字段在这里写清楚，让 Agent 不用猜
#   * 不要出现 Multisim 内部概念（参数序号、CiID、SimState、探针的 LocalName）
# ---------------------------------------------------------------------------
_CID = {"type": "string",
        "description": "create_circuit 返回的 circuit_id，形如 c-1a2b3c4d5e"}

_SIM_ID = {"type": "string",
           "description": "simulate 返回的 sim_id，形如 s-1a2b3c4d5e"}

_PROBE_ID = {
    "type": "string",
    "description": (
        "探针的 probe_id（如 P1），就是 add_probe 里 name 给的那个、"
        "simulate 返回的 probes[].probe_id。**不是** Multisim 的显示名"
        "（探针1）或输出名（V(探针1)）—— 传错会返回 PROBE_NOT_FOUND，"
        "并在 hint 里告诉你正确的 probe_id。"
    ),
}

# ---------------------------------------------------------------------------
# add_component 的元件清单
#
# 手写的 5 条写在下面（它们的语义、单位是人定的）；registry 里 enable 的
# 元件由 S.REGISTRY_PART_SPEC 自动生成 —— 引脚、donor、SPICE 模板都来自
# 真实 .ms14，不手抄。这样"新增一种元件"就不需要改这段文案，
# 也就不会出现"文档写了但代码没实现"。
# ---------------------------------------------------------------------------
_REGISTRY_NOTES = {
    ("DIODE", "1N4007G"): (
        "只支持一种拓扑：V1 -> D1 -> R1 -> GND 的半波整流"
        "（D1.A 接源正极，D1.K 接负载电阻的一端，电阻另一端接 GND）。"
        "其它二极管接法会返回 LAYOUT_UNSUPPORTED，context.reason 说明是哪一类没验过。"
    ),
}


def _registry_part_doc():
    lines = []
    for key in S.REGISTRY_PART_META:
        fam, part = key
        e = S.REGISTRY_PART_SPEC.get(key) or {}
        pins = "/".join(e.get("pins") or [])
        donor = os.path.basename(((e.get("donor") or {}).get("file")) or "?")
        dref = (e.get("donor") or {}).get("refdes") or "?"
        bits = ["  family=%s, part=%s" % (fam, part)]
        bits.append("（引脚 %s，**不接受 value**" % pins)
        if e.get("spice_template"):
            bits.append("；SPICE 模板 `%s`" % e["spice_template"])
        bits.append("；donor %s[%s]）\n" % (donor, dref))
        line = "".join(bits)
        note = _REGISTRY_NOTES.get(key)
        if note:
            line += "    ⚠️ %s\n" % note
        lines.append(line)
    return "".join(lines)


_TOOL_DESC_ADD_COMPONENT = (
    "往电路里加一个元件。只接受已验证过真机仿真的 %d 种（family 和 part 是"
    "**两个独立字段**，不要把斜杠连写当成一个值）：\n"
    "  family=SIGNAL_VOLTAGE_SOURCES, part=AC_VOLTAGE"
    "（正弦源，value=幅值V，parameters={'frequency': Hz}）\n"
    "  family=POWER_SOURCES, part=DC_POWER（直流源，value=电压V）\n"
    "  family=RESISTOR, part=RESISTOR_VIRTUAL（value=阻值 Ω）\n"
    "  family=CAPACITOR, part=CAPACITOR_VIRTUAL（value=容值 F）\n"
    "  family=POWER_SOURCES, part=GROUND（不需要 value）\n"
    "%s"
    "引脚（connect 里用）：AC_VOLTAGE / DC_POWER 是 '1' '2'，"
    "另有别名 '+'->'1'、'-'->'2'；电阻 / 电容只有 '1' '2'，**没有 +/- 别名**；"
    "GROUND 只有 '1'；二极管是 'A' 'K'（阳极 / 阴极，**没有别名**）。\n"
    "不要传坐标 —— 布局由 simulate 自动算。refdes 不传就自动编号。\n"
    "返回的 component 是固定形状：refdes / family / part / value / "
    "value_name / value_unit / parameters / pins / aliases。"
    "parameters 的键永远是语义名（frequency），不会是数字序号。"
) % (len(S.PART_META), _registry_part_doc())

TOOLS = [
    {
        "name": "create_circuit",
        "description": (
            "创建一个新的空电路会话，返回 circuit_id。之后所有 add_component / "
            "connect / add_probe 都要带上这个 id。不会立刻生成 .ms14 —— "
            "编译发生在 simulate 时。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "给电路起个名字（可读，会用于产物文件名）"},
            },
        },
    },
    {
        "name": "add_component",
        "description": _TOOL_DESC_ADD_COMPONENT,
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "family": {"type": "string",
                           "description": "元件家族，如 RESISTOR / POWER_SOURCES"},
                "part": {"type": "string",
                         "description": "具体型号，如 RESISTOR_VIRTUAL / DC_POWER"},
                "refdes": {"type": "string",
                           "description": "位号（V1 / R1 / C1 / GND1）。不传则自动编号"},
                "value": {"type": "number",
                          "description": (
                              "元件的主值。语义由元件类型决定（AC_VOLTAGE=幅值V / "
                              "DC_POWER=电压V / 电阻=Ω / 电容=F）。返回的 "
                              "component.value_name + value_unit 会明确告诉你它是"
                              "什么，不用猜。")},
                "parameters": {"type": "object",
                               "description": (
                                   "附加参数，键是语义名。目前只有 AC_VOLTAGE 用得上："
                                   '{"frequency": 1000}（单位 Hz）。'
                                   "键写错会返回 UNKNOWN_PARAMETER 并列出可用参数。"
                                   "**不要在键里写数字序号**（如 {\"5\": 1000}）。")},
                "frequency": {"type": "number",
                              "description": (
                                  "parameters={'frequency': ...} 的便捷写法，"
                                  "两者等价，**不要同时传**。")},
            },
            "required": ["circuit_id", "family", "part"],
        },
    },
    {
        "name": "connect",
        "description": (
            "把若干引脚连到同一条网络上。引脚写法：[\"V1\",\"+\"] 或 \"V1.+\"。\n"
            "网络名可以不给：含地的网络会自动叫 '0'，含电源正极的自动叫 'in'，"
            "其余 n1/n2。\n"
            "显式给 net 时：**这个名字已经存在就追加**（把新引脚并进那条网络），"
            "不存在就新建 —— 返回顶层 created=true/false 告诉你走的是哪条路。\n"
            "同一个引脚不能属于两条网络。不要传坐标。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "pins": {"type": "array",
                         "description": "引脚数组，如 [[\"V1\",\"+\"],[\"R1\",\"1\"]]",
                         "items": {}},
                "net": {"type": "string",
                        "description": "网络名。不传则自动命名"},
            },
            "required": ["circuit_id", "pins"],
        },
    },
    {
        "name": "add_probe",
        "description": (
            "在某个网络上放一个电压探针。target 可以是网络名（'out'）、"
            "引脚（'R1.2'，自动解析成它所在的网络）。\n"
            "不要传元件位号（'R1'）—— 两端元件有两个引脚，会报 AMBIGUOUS_TARGET。\n"
            "最多 9 个探针（超过 9 个时的命名规则还没验证）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "target": {"type": "string",
                           "description": "网络名（'in'）或引脚（'R1.2'）"},
                "name": {"type": "string",
                         "description": ("探针的 probe_id（也是它的名字）。不传则自动编号 "
                                         "P1/P2/...。之后 measure / get_waveform "
                                         "都用这个 ID 指定通道。")},
            },
            "required": ["circuit_id", "target"],
        },
    },
    {
        "name": "get_circuit",
        "description": (
            "只读地取回一个电路当前的状态，不改变任何东西。\n"
            "什么时候用：改了电路想确认现在长什么样；隔了几轮对话只记得 "
            "circuit_id；想在动手前先看看已经有什么。\n"
            "返回和 create / add_component / connect 完全相同的快照结构："
            "components / nets / probes / topology / simulation / simulations / "
            "counts / warnings。如果这个电路已经仿真过，probes[] 里的 label / output "
            "会被填上（否则是 null）。\n"
            "topology 是后端对你这个电路的拓扑判断：kind（shunt_load / "
            "series_chain / divider / bypass / tee / ladder）、n_series、n_shunt、"
            "stages[]、out_net。它有两个**互相独立**的布尔值：\n"
            "  supported —— 这种拓扑布局引擎认不认（不认时 reason 说明是哪一类）；\n"
            "  complete  —— 电路接完了没有（没接完时 issues 列出还差什么）。\n"
            "两个都是 false 是正常状态，不是错误。supported=true 但 complete=false "
            "意味着\"能摆得下，但还有引脚悬空\"，这时候 simulate 会被 validate 拦住。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"circuit_id": _CID},
            "required": ["circuit_id"],
        },
    },
    {
        "name": "simulate",
        "description": (
            "编译并真跑 Multisim，返回仿真句柄 sim_id。\n"
            "analysis 可选 transient（时域）或 dc（直流工作点，单点）。\n"
            "源类型与分析的匹配是强制的：AC_VOLTAGE 只能 transient，"
            "DC_POWER 默认 dc（也允许 transient）。不匹配会返回 "
            "ANALYSIS_NOT_SUPPORTED 并告诉你该改成什么。\n"
            "transient 不传 stop / sample_rate 时按信号频率自动推算（6 个周期、"
            "每周期 200 点）。这三个参数都**沿用 IR 里上次的值**（第一次才自动推算），"
            "想换窗口就显式传，别指望它自己重置。\n"
            "start 是**导出窗口的起点**：仿真本身仍然从 t=0 算起"
            "（Multisim COM 没有\"从 t0 起算\"的入口），返回的波形和 CSV 会裁掉 "
            "t < start 的采样点 —— 用它跳过启动暂态，不要指望它省计算时间。\n"
            "这个调用是阻塞的，实测单次 30 s 左右（编译 + 启 Multisim + 读数）。"
            "返回里带 timing（layout_s / compile_s / run_s / total_s），"
            "可以用它判断电路复杂度和该给多少超时。"
            "返回里的 ms14 / waveform / record 是**相对仓库根目录**的路径。\n"
            "返回里还带 topology（这次仿真按什么拓扑布局的）。拓扑不在支持范围"
            "内时不会硬跑，而是返回 LAYOUT_UNSUPPORTED + context.reason；"
            "reason 有 fork（一个节点两条主干）/ parallel_shunt（同一节点 3 个及以上"
            "到地元件；2 个已支持）/ island（元件和电源不连通）/ too_many_stages 等。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "analysis": {"type": "string", "enum": ["transient", "dc"],
                             "description": "分析类型。不传则按源类型自动选"},
                "start": {"type": "number", "description": "起始时间 s（仅 transient）"},
                "stop": {"type": "number", "description": "结束时间 s（仅 transient）"},
                "sample_rate": {"type": "number",
                                "description": "采样率 Hz（仅 transient）"},
                "timeout": {"type": "number",
                            "description": (
                                "软超时，单位秒。只在阶段之间（布局 / 编译 / 跑仿真）"
                                "检查，**无法中断已经开始的 Multisim 调用**；"
                                "超了返回 SIMULATION_TIMEOUT 并带上已用时间。"
                                "不传则不限制。")},
            },
            "required": ["circuit_id"],
        },
    },
    {
        "name": "measure",
        "description": (
            "从一次仿真里取测量值。what 决定返回哪些字段：\n"
            "  all（默认）      全部：均值 / RMS / 幅值 / 相位 / 增益\n"
            "  voltage          每通道的 mean / rms / min / max\n"
            "  amplitude        每通道的正弦拟合幅值（仅 transient）\n"
            "  phase            每通道相位（仅 transient）\n"
            "  dc_voltage       每通道直流电压（仅 dc）\n"
            "transient 会额外给 gain / phase_deg / theory；dc 会给 "
            "v_resistor / current（I = V_R / R，R 是 Multisim 读回来的实际阻值，\n"
            "用 r_source 标明来源：multisim / ir）。\n"
            "**gain 的方向由拓扑决定，不由探针添加顺序决定**：输入探针取源正极"
            "所在网络，输出探针取 topology.out_net；两个都找到时 pairing=\"topology\"。"
            "找不到（比如只有一个探针）时退回 absolute 模式（以源声明的幅值为参考）"
            "并在 pairing / notes 里说明。\n"
            "**例外：半波整流电路（topology.kind=\"halfwave_rectifier\"）不做正弦"
            "拟合，也没有 gain / phase_deg。** 整流后的波形不是单一正弦，拟合出的"
            "幅值没有物理意义。这时 mode=\"rectifier\"，返回：\n"
            "  v_out_peak / v_out_min / v_out_mean   峰值 / 最小值 / 直流分量\n"
            "  vf_deep_on                            深导通区逐点压降（mean/std/min/max）\n"
            "  reverse_block_max                     反偏区输出的绝对值上界（应 ≈ 0）\n"
            "  conduction_frac                       导通占比\n"
            "  theory + bracket                      **区间而不是点值**：\n"
            "      v_dc ∈ [Vm/π - Vf/2, Vm/π]，导通占比 ∈ [恒定压降模型, 0.5]。\n"
            "      bracket.pos 表示实测偏向哪一端（0 = 恒定压降端，1 = 理想二极管端）。\n"
            "      恒定压降假设只在深导通区成立，别拿它当点值对账。\n"
            "每通道的 mean 是**全窗算术平均**（含启动暂态，不一定接近 0）；"
            "offset 才是正弦拟合出来的直流分量。两者含义不同，别当成同一件事。\n"
            "channels 是以 **probe_id 为键** 的对象，和 get_waveform 的 channels "
            "完全一致；每个通道固定带 probe_id / label / output / net / kind，"
            "再叠加测量字段（what 过滤不会删掉身份字段）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sim_id": _SIM_ID,
                "what": {"type": "string",
                         "enum": ["all", "voltage", "amplitude", "phase",
                                  "dc_voltage"]},
                "probe_id": _PROBE_ID,
            },
            "required": ["sim_id"],
        },
    },
    {
        "name": "get_waveform",
        "description": (
            "取波形数据。不会把整条波形塞进返回值：默认只给摘要（n / min / max / "
            "mean / 时间范围）+ 最多 max_points 个采样点的预览，完整数据在 "
            "artifact 指向的 CSV 里（路径相对仓库根目录）。\n"
            "预览是在整段窗口上均匀取点（含首尾），不是按整数步长抽样 —— "
            "整数步长会和信号周期重合，画出来可能是一条水平线（假象）。"
            "要看真实波形就打开 artifact 的 CSV。\n"
            "channels 是以 **probe_id 为键** 的对象，和 measure 的 channels "
            "完全一致 —— 两个工具的通道可以直接对照，不需要自己映射。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sim_id": _SIM_ID,
                "probe_id": _PROBE_ID,
                "max_points": {"type": "integer",
                               "description": "预览采样点上限，默认 200，最大 5000"},
            },
            "required": ["sim_id"],
        },
    },
]

_DISPATCH = {
    "create_circuit": S.create_circuit,
    "add_component": S.add_component,
    "connect": S.connect,
    "add_probe": S.add_probe,
    "get_circuit": S.get_circuit,
    "simulate": S.simulate,
    "measure": S.measure,
    "get_waveform": S.get_waveform,
}


# ---------------------------------------------------------------------------
# JSON-RPC
# ---------------------------------------------------------------------------
def _send(obj):
    line = json.dumps(obj, ensure_ascii=False)
    _PROTO_OUT.write(line + "\n")
    _PROTO_OUT.flush()


def _ok(rid, result):
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _fail(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _send({"jsonrpc": "2.0", "id": rid, "error": err})


def _text_result(payload, is_error=False):
    """MCP tools/call 的返回：content 文本 + structuredContent 两份都给。

    文本那份是给只看 content 的客户端；structuredContent 给能解析结构的客户端。
    两份内容一致，避免 Agent 在不同客户端上看到不同的东西。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    out = {"content": [{"type": "text", "text": text}]}
    if isinstance(payload, dict):
        out["structuredContent"] = payload
    if is_error:
        out["isError"] = True
    return out


def _call_tool(name, args):
    fn = _DISPATCH.get(name)
    if fn is None:
        return _text_result({"ok": False,
                             "error": {"code": "UNKNOWN_TOOL",
                                       "message": "没有这个工具：%r" % name,
                                       "hint": "可用：%s" % ", ".join(_DISPATCH)}},
                            is_error=True)
    try:
        payload = fn(**args)
        if isinstance(payload, dict):
            payload.setdefault("ok", True)
        return _text_result(payload)
    except S.SessionError as e:
        return _text_result({"ok": False, "error": e.to_dict()}, is_error=True)
    except TypeError as e:
        return _text_result(
            {"ok": False,
             "error": {"code": "BAD_ARGUMENT",
                       "message": "参数不对：%s" % e,
                       "hint": "对照 tools/list 里这个工具的 inputSchema。"}},
            is_error=True)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return _text_result(
            {"ok": False,
             "error": {"code": "INTERNAL", "message": "%s: %s"
                        % (type(e).__name__, e),
                        "hint": "这是内部错误，不是你的参数问题；"
                                "看 server 的 stderr。"}},
            is_error=True)


def handle(msg):
    if not isinstance(msg, dict):
        return
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}

    # 通知（没有 id）不需要响应
    is_notification = "id" not in msg

    if method == "initialize":
        _ok(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "这是 Multisim 电路执行器。典型流程："
                "create_circuit -> add_component × N -> connect -> add_probe -> "
                "simulate -> measure / get_waveform；"
                "get_circuit 可以随时只读取回当前电路状态。"
                "不要传坐标，布局由 simulate 自动算。"
                "探针只有 probe_id 一个身份（P1），measure / get_waveform "
                "都用它指定通道，不要用 Multisim 的显示名或输出名。"
                "只支持单电源、单主干 + 到地并联支路的拓扑"
                "（分压 / 旁路电容 / T 型 / 多级 RC 梯形 / 半波整流 / "
                "同一节点最多 2 个到地元件，比如分压 + 旁路电容）；"
                "一个节点分出两条主干（fork）、同一节点 3 个及以上到地元件、"
                "反馈、多电源会报 LAYOUT_UNSUPPORTED，context.reason 说明属于哪一类。"
                "每个状态快照里都带 topology 字段，可以先看后端认为你搭的是"
                "什么拓扑，再决定要不要 simulate。"
            ),
        })
        return

    if is_notification:
        return

    if method == "ping":
        _ok(rid, {})
        return

    if method == "tools/list":
        _ok(rid, {"tools": TOOLS})
        return

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            _fail(rid, -32602, "arguments 必须是对象")
            return
        _ok(rid, _call_tool(name, args))
        return

    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        _ok(rid, {key: []})
        return

    _fail(rid, -32601, "Method not found: %r" % method)


def main():
    print("[mcp] %s v%s 就绪（python %s, %d 位）"
          % (SERVER_NAME, SERVER_VERSION, sys.version.split()[0],
             64 if sys.maxsize > 2 ** 32 else 32), file=sys.stderr)
    print("[mcp] 会话目录 %s" % S.SESS_ROOT, file=sys.stderr)
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            _fail(None, -32700, "JSON 解析失败：%s" % e)
            continue
        if isinstance(msg, list):
            for m in msg:
                handle(m)
        else:
            handle(msg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
