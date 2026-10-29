# -*- coding: utf-8 -*-
"""拓扑分析 + 坐标布局（v0.7.0：P2 branch-aware layout）。

为什么单独一个模块
------------------
**拓扑判断先于坐标布局。** 这是这一版最重要的结构决定：

    Circuit IR
      -> analyze()      纯图论：这是什么拓扑？支路在哪？属于哪个模板？
      -> Topology       结构化描述（stages / shunt / 输出网）
      -> plan()         按拓扑生成坐标
      -> {refdes: [x, y]}
      -> ir_compile     -> .ms14

如果顺序反过来（先试着摆坐标、摆不下再报错），错误会落在坐标层，
而真正的问题是"拓扑没被表达"。等以后支持运放、反馈、桥式电路时，
这个差别会变成"每次加一种电路都要改坐标代码"还是"只加一个模板"。
所以这里彻底分开：`analyze()` 不认识坐标，`plan()` 不认识电路语义。

一条必须说清楚的事实（实测，见 docs/layout.md）
----------------------------------------------
**坐标不影响连通性。** `ir_compile` 建网表用的是 nets 里显式的引脚列表
（`msbuild.connect(members)`），坐标只决定符号画在哪、导线连成什么折线。
所以布局器的职责是两件：

  1. 准入门槛 —— 这个拓扑我们验过吗？没验过就明确拒绝，不硬排；
  2. 可读坐标 —— 给一套不重叠、能看出层级的坐标。

它**不负责**"把电路连对"。这一点很关键：它意味着 P2 的风险不在电气，
而在"准入判断写得准不准"。

支持的拓扑类：单主干 + 到地并联支路（ladder）
--------------------------------------------
一条从电源正极出发、逐级向下的主干；每级最多一个到地的并联元件；
电源负极接地。三个具名模板是它的特例：

    kind            结构                          例子
    --------------  ----------------------------  ----------------------
    shunt_load      0 串联 + 1 到地               直流源 + 一个电阻
    series_chain    N 串联 + 0 到地               分压的上半臂 / 空载串联
    divider         1 串联 + 1 到地(电阻)         电阻分压
    bypass          1 串联 + 1 到地(电容)         一阶 RC 低通
    tee             2 串联 + 1 到地(电阻，中间级)  T 型网络
    ladder          其它（≥2 串联，≥1 到地）      二阶 RC 梯形
    halfwave_rectifier  1 二极管串联 + 1 电阻到地  半波整流（v0.9 新增）
    parallel_shunt  某节点挂 2 个到地元件         分压 + 旁路电容 / RC 并联负载
                                                  （v0.10.0 新增）

`halfwave_rectifier` 是唯一走 `KIND_TEMPLATES` 模板表的拓扑，也是唯一带
**准入闸门**的拓扑（`_check_diode_topology`）：其余 6 类只要结构对上就放行，
二极管则必须精确匹配那一种接法。原因见该函数的 docstring。

v0.10.0 起多了一条：**同一节点最多 2 个到地元件**（`parallel_shunt`）。

这是教学电路里出现频率最高的一类形状 —— 分压器 + 旁路电容、RC 并联负载、
电阻并联做等效值，全都是"一个节点上两个元件一起下地"。它的几何只是把
第 2 个元件在同一行往右挪半格（`SHUNT_DX`），不改动任何已验收的坐标。

明确拒绝（不是"排不出来"，是"这类拓扑还没验过"）：

    reason           含义
    --------------  --------------------------------------------
    fork            一个节点有 2 条向下的主干（真正的并联支路 / 跨级连接）
    parallel_shunt  一个节点有 3 个及以上到地元件（2 个已放开）
    island          元件和电源不连通（悬空 / 独立子电路）
    cycle           拓扑回到走过的节点（环路 / 反馈）
    open_pin        元件的另一端没接线
    too_many_stages 主干级数超过验证范围
"""
import circuit_ir as irmod


# 主干级数上限。不是技术极限（坐标是装饰性的），是"验过的范围"：
# 超过 4 级时符号排布是否还看得清，没实测过。
MAX_STAGES = 4
MAX_SHUNTS = 4

# 同一节点上最多几个到地元件（v0.10.0）。1 个是 v0.1~v0.9 就支持的形状，
# 2 个是这一版放开的"并联到地"；3 个及以上没验过，明确拒绝。
MAX_SHUNTS_PER_NODE = 2

# 坐标网格。源独占最左一列，各级从源右边一格开始；串联元件在级与级之间，
# 并联元件挂在级列正下方，地在左下。
#
# ⚠️ 为什么各级要从 X0 + DX 开始，而不是 X0：
# 一开始把第 0 级放在 X0（也就是源的正下方），结果直流电路（源 + 一个到地
# 电阻）的 `0` 网导线从电阻下引脚竖直向上走回源负极，**横穿了电阻自己的
# 符号框**，Multisim 只认出一个探针通道（`outputs=["V(探针1)"]`）。
# 实测证据见 docs/layout.md 第 6 节。把各级右移一格后导线不再穿任何符号。
X0 = 300.0
DX = 240.0
Y_MAIN = 300.0
Y_SHUNT = 460.0
Y_GND = 620.0

# 同一节点上第 2 个到地元件相对本级的水平偏移（v0.10.0）。
#
# 取值 DX/2 = 120：元件符号宽约 40~60，120 的间距让两个符号之间留出
# 一条能看见的竖线，又不会挤到隔壁级的列（隔壁列在 ±DX）。两个元件
# 摆在同一行 Y_SHUNT 上，"并联"这件事在图上是一眼能看出来的横排。
SHUNT_DX = DX / 2.0


# ---------------------------------------------------------------------------
# 模板表（v0.9 新增）
#
# **只有半波整流这一条走模板表，其余 6 类仍然走 plan() 里的通用规则。**
# 这么做不是为了"通用"，恰恰是为了不通用：v0.1~v0.8 验证过的 6 类拓扑坐标
# 一个字节都不许变（改了就等于动了已验收的行为），而新拓扑需要一块能单独
# 描述、单独测试、单独演进的地方。
#
# 偏移量是相对本级列的：(DX 的比例, Y 偏移)。
# ---------------------------------------------------------------------------
KIND_TEMPLATES = {
    "halfwave_rectifier": {
        "series_offset": (0.5, 0.0),     # 二极管放在"本级 -> 下一级"的中间
        "shunt_offset": (0.0, 0.0),      # 负载电阻挂在本级正下方
        "note": ("V1 -> D1 -> R1 -> GND。几何沿用已验收的 bypass/divider 两端口"
                 "排布：串联位在行上，到地位在下一列正下方。"
                 "二极管 donor 是竖直符号（A 在下、K 在上），导线会从上下两端"
                 "进出 —— 坐标不影响连通性（见文件头），只影响观感。"),
    },
}


def _col_x(index):
    """第 index 级所在的列。源占 X0，所以第 0 级从 X0 + DX 开始。"""
    return X0 + DX * (index + 1)


class LayoutError(Exception):
    """布局 / 拓扑层自己的错误类型。

    故意不依赖 circuit_session.SessionError：这一层要能在不 import
    会话层的情况下单独测试。会话层负责把它转成对外的结构化错误。
    """

    def __init__(self, code, message, hint=None, **context):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.hint = hint
        self.context = context

    def to_dict(self):
        d = {"code": self.code, "message": self.message}
        if self.hint:
            d["hint"] = self.hint
        if self.context:
            d["context"] = self.context
        return d

    def __str__(self):
        return "%s: %s" % (self.code, self.message)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
class Stage(object):
    """主干上的一级。

    `net`    这一级对应的网络
    `series` 从这一级往下走的串联元件（最后一级没有）
    `shunts` 挂在这一级到地的并联元件（0 个、1 个，或 v0.10.0 起的 2 个）

    `shunt` 是 `shunts[0]` 的只读别名 —— v0.1~v0.9 的代码、测试、文档都只认
    "一级一个到地元件"，保留它可以让那些地方一个字节都不用改。新代码请用
    `shunts`，别再用 `shunt`（它会悄悄忽略第 2 个元件）。
    """

    __slots__ = ("index", "net", "series", "shunts")

    def __init__(self, index, net, series=None, shunts=None):
        self.index = index
        self.net = net
        self.series = series
        self.shunts = list(shunts or ())

    @property
    def shunt(self):
        """第一个到地元件；没有则 None。**只看第一个**，见类 docstring。"""
        return self.shunts[0] if self.shunts else None

    def to_dict(self):
        return {"index": self.index, "net": self.net,
                "series": self.series, "shunt": self.shunt,
                "shunts": list(self.shunts)}

    def __repr__(self):
        return "Stage(%d, %r, series=%r, shunts=%r)" % (
            self.index, self.net, self.series, self.shunts)


class Topology(object):
    """`analyze()` 的产物。只描述结构，不含任何坐标。"""

    def __init__(self, kind, source, ground, in_net, gnd_net, stages, out_net):
        self.kind = kind
        self.source = source
        self.ground = ground
        self.in_net = in_net
        self.gnd_net = gnd_net
        self.stages = stages
        self.out_net = out_net

    @property
    def n_series(self):
        return max(0, len(self.stages) - 1)

    @property
    def n_shunt(self):
        """到地元件的**个数**（不是有到地的级数）。"""
        return sum(len(s.shunts) for s in self.stages)

    @property
    def elements(self):
        """主干 + 并联的全部元件位号，按信号流向。"""
        out = []
        for s in self.stages:
            if s.series:
                out.append(s.series)
            out.extend(s.shunts)
        return out

    def to_dict(self):
        return {
            "kind": self.kind,
            "source": self.source,
            "ground": self.ground,
            "in_net": self.in_net,
            "gnd_net": self.gnd_net,
            "out_net": self.out_net,
            "n_series": self.n_series,
            "n_shunt": self.n_shunt,
            "stages": [s.to_dict() for s in self.stages],
        }

    def summary(self):
        lines = ["拓扑 %s：%d 级主干 / %d 个到地支路"
                 % (self.kind, self.n_series, self.n_shunt),
                 "  %s(+) -> %s" % (self.source, self.in_net)]
        for s in self.stages:
            bits = ["[%d] %s" % (s.index, s.net)]
            if s.series:
                bits.append("--%s--> " % s.series)
            if s.shunts:
                bits.append("|%s->%s" % ("||".join(s.shunts), self.gnd_net))
            lines.append("  " + " ".join(bits))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _pins_of(comp):
    spec = irmod.SUPPORTED.get((comp.family, comp.part)) or {}
    return list(spec.get("pins") or ())


def _pin_net(ir, refdes, pin):
    for n in ir.nets:
        for r, p in n.refs():
            if r == refdes and p == pin:
                return n.name
    return None


def _two_pin_other(comp, pin):
    """两端元件里"另一个"引脚名；不是两端元件返回 None。"""
    pins = _pins_of(comp)
    real = irmod._norm_pin(comp, pin)
    others = [p for p in pins if p != real]
    return others[0] if len(others) == 1 else None


def _sources(ir):
    return [c for c in ir.components
            if c.part != "GROUND"
            and c.family in ("POWER_SOURCES", "SIGNAL_VOLTAGE_SOURCES")]


def _grounds(ir):
    return [c for c in ir.components if c.part == "GROUND"]


def _source_pins(comp):
    """(正极引脚名, 负极引脚名)。"""
    spec = irmod.SUPPORTED.get((comp.family, comp.part)) or {}
    al = spec.get("aliases") or {}
    return al.get("+", "1"), al.get("-", "2")


def _is_resistor(comp):
    return comp is not None and comp.family == "RESISTOR"


def _is_diode(comp):
    return comp is not None and comp.family == "DIODE"


def _is_capacitor(comp):
    return comp is not None and comp.family == "CAPACITOR"


def _unsupported(reason, message, hint, **context):
    ctx = {"reason": reason}
    ctx.update(context)
    return LayoutError("LAYOUT_UNSUPPORTED", message, hint, **ctx)


# ---------------------------------------------------------------------------
# 第一步：拓扑分析（不认识坐标）
# ---------------------------------------------------------------------------
def analyze(ir):
    """把 Circuit IR 解析成 `Topology`。不支持的拓扑抛 `LayoutError`。"""
    srcs = _sources(ir)
    if not srcs:
        raise LayoutError("NO_SOURCE", "电路里没有电源",
                          "先 add_component 一个 DC_POWER 或 AC_VOLTAGE。")
    if len(srcs) > 1:
        raise LayoutError(
            "MULTIPLE_SOURCES",
            "电路里有 %d 个电源（%s）"
            % (len(srcs), ", ".join(c.refdes for c in srcs)),
            "P2 只支持单电源。多电源（含运放双电源供电）还没验证过。",
            sources=[c.refdes for c in srcs])
    src = srcs[0]

    gnds = _grounds(ir)
    if not gnds:
        raise LayoutError("NO_GROUND", "电路里没有接地元件",
                          "加一个 POWER_SOURCES/GROUND，并把回路接上去。")
    if len(gnds) > 1:
        raise LayoutError("MULTIPLE_GROUND",
                          "电路里有 %d 个 GROUND" % len(gnds),
                          "第一版只支持一个接地元件（位号 %s）。"
                          % ", ".join(g.refdes for g in gnds))
    gnd = gnds[0]
    gnd_pin = _pins_of(gnd)[0]
    gnd_net = _pin_net(ir, gnd.refdes, gnd_pin)
    if gnd_net is None:
        raise LayoutError("GROUND_NOT_CONNECTED",
                          "接地元件 %s 还没接到任何网络" % gnd.refdes,
                          "把回路的一个节点接到 %s.1。" % gnd.refdes,
                          refdes=gnd.refdes)

    pos_pin, neg_pin = _source_pins(src)
    in_net = _pin_net(ir, src.refdes, pos_pin)
    if in_net is None:
        raise LayoutError("SOURCE_NOT_CONNECTED",
                          "电源 %s 的正极还没接线" % src.refdes,
                          "先 connect 电源正极和下一个元件。",
                          refdes=src.refdes, pin=pos_pin)
    neg_net = _pin_net(ir, src.refdes, neg_pin)
    if neg_net != gnd_net:
        raise LayoutError(
            "SOURCE_NOT_GROUNDED",
            "电源 %s 的负极没接到地（在 %r，地是 %r）"
            % (src.refdes, neg_net, gnd_net),
            "P2 假设单电源：负极必须和 GROUND 同网络。"
            "先 connect [%s.-, %s.1]。" % (src.refdes, gnd.refdes),
            refdes=src.refdes, neg_net=neg_net, gnd_net=gnd_net)

    visited = {src.refdes, gnd.refdes}
    stages = []
    seen_nets = set()
    cur = in_net

    for depth in range(64):
        if cur in seen_nets:
            raise _unsupported(
                "cycle",
                "拓扑回到了已经走过的节点 %r，有环路" % cur,
                "P2 不支持环路 / 反馈。把反馈断开，或先只验前向通路。",
                net=cur)
        seen_nets.add(cur)

        net = ir.net(cur)
        if net is None:
            raise LayoutError("INTERNAL", "网络 %r 不存在" % cur)

        series, shunts = [], []
        for ref, pin in net.refs():
            if ref in visited:
                continue
            comp = ir.component(ref)
            if comp is None:
                raise LayoutError("INTERNAL",
                                  "网络 %r 引用了不存在的元件 %r" % (cur, ref))
            other = _two_pin_other(comp, pin)
            if other is None:
                raise _unsupported(
                    "non_two_pin",
                    "网络 %r 上的 %s 不是两端元件（%s/%s）"
                    % (cur, ref, comp.family, comp.part),
                    "P2 的布局只认两端元件：电阻、电容、电源、地。",
                    net=cur, refdes=ref)
            onet = _pin_net(ir, ref, other)
            if onet is None:
                raise _unsupported(
                    "open_pin",
                    "%s 的另一个引脚（%s.%s）还没接线" % (ref, ref, other),
                    "布局要求每个元件的两端都接到网络。",
                    net=cur, refdes=ref)
            (shunts if onet == gnd_net else series).append((ref, onet))

        if len(series) > 1:
            raise _unsupported(
                "fork",
                "网络 %r 有 %d 条向下的主干（%s）"
                % (cur, len(series), ", ".join(r for r, _ in series)),
                "P2 支持『单主干 + 到地并联』：一个节点只能有一条向下的主干。"
                "两条并排的支路（比如两组 RC 并联）还没验证过。"
                "如果本意是并联，把其中一条改成到地的旁路。",
                net=cur, branches=[r for r, _ in series])
        if len(shunts) > MAX_SHUNTS_PER_NODE:
            raise _unsupported(
                "parallel_shunt",
                "网络 %r 有 %d 个到地元件（%s），超过上限 %d 个"
                % (cur, len(shunts), ", ".join(r for r, _ in shunts),
                   MAX_SHUNTS_PER_NODE),
                "一个节点上最多挂 %d 个到地元件（v0.10.0 放开到 2 个："
                "电阻并联、电阻并联电容都验过）。%d 个及以上还没验过，"
                "先把其中几个合并成一个等效元件。"
                % (MAX_SHUNTS_PER_NODE, MAX_SHUNTS_PER_NODE + 1),
                net=cur, shunts=[r for r, _ in shunts],
                limit=MAX_SHUNTS_PER_NODE)

        st = Stage(index=depth, net=cur, shunts=[r for r, _ in shunts])
        for r, _ in shunts:
            visited.add(r)
        if not series:
            stages.append(st)
            break
        st.series = series[0][0]
        visited.add(st.series)
        stages.append(st)
        cur = series[0][1]
    else:
        raise _unsupported("cycle", "拓扑遍历没有收敛（可能有环）",
                           "P2 不支持环路 / 反馈。")

    # ---------- 覆盖检查：所有元件都必须在主干或支路上 ----------
    #
    # 走到这里还有"没被访问过"的元件，说明它和电源正极不连通。
    # （真正跨级的元件在主干上一定会被"一个节点只能有一条向下的主干"拦下来，
    #  所以不需要单独判 cross_link —— 那种情况报 fork 更准确。）
    leftover = [c.refdes for c in ir.components if c.refdes not in visited]
    if leftover:
        raise _unsupported(
            "island",
            "这些元件和电源不连通（%s）" % ", ".join(leftover),
            "P2 只支持从电源正极一路走到地的连通拓扑。悬空元件、"
            "独立子电路、以及和电源不连通的部分都还不支持。",
            components=leftover)

    if len(stages) - 1 > MAX_STAGES:
        raise _unsupported(
            "too_many_stages",
            "主干有 %d 级，超过验证上限 %d 级" % (len(stages) - 1, MAX_STAGES),
            "不是技术上做不到，是超过 %d 级时符号排布没实测过。"
            "先拆成子电路分别验。" % MAX_STAGES,
            count=len(stages) - 1, limit=MAX_STAGES)
    if sum(len(s.shunts) for s in stages) > MAX_SHUNTS:
        raise _unsupported(
            "too_many_shunts",
            "到地元件有 %d 个，超过验证上限 %d 个"
            % (sum(len(s.shunts) for s in stages), MAX_SHUNTS),
            "同上：不是做不到，是没验过。", limit=MAX_SHUNTS)

    kind = _classify(ir, stages)
    if _diode_refs(ir):
        _check_diode_topology(ir, stages, kind)
    return Topology(kind=kind, source=src.refdes, ground=gnd.refdes,
                    in_net=in_net, gnd_net=gnd_net, stages=stages,
                    out_net=stages[-1].net)


def _diode_refs(ir):
    return [c.refdes for c in ir.components if c.family == "DIODE"]


def _check_diode_topology(ir, stages, kind):
    """二极管的准入闸门（v0.9）。

    二极管在 donor 里是**竖直符号**（A 在下、K 在上），和已经验过的电阻/电容
    朝向不同；而且"整流"这件事没法用正弦拟合去验证（`measure` 会走专门分支）。
    所以这一版**只放开一种拓扑**：

        V1 -> D1 -> R1 -> GND     （1 个二极管串联 + 1 个电阻到地）

    其余任何带二极管的接法一律明确拒绝，并说清是哪一类还没验过 ——
    不做"大概能摆"的猜测。这是刻意的：先把一种拓扑做到电气可验证，
    再谈通用。
    """
    ds = _diode_refs(ir)
    shunts = [s for s in stages if s.shunt]
    series = [s.series for s in stages if s.series]

    def reject(reason, message, hint):
        raise _unsupported(reason, message, hint,
                           diodes=ds,
                           series=series, shunts=[s.shunt for s in shunts])

    if len(ds) > 1:
        reject("diode_multiple",
               "电路里有 %d 个二极管（%s）" % (len(ds), ", ".join(ds)),
               "v0.9 只验证过单个二极管的半波整流。"
               "全波整流 / 桥式整流还没验过。")

    if any(_is_capacitor(c) for c in ir.components):
        reject("diode_with_capacitor",
               "二极管电路里出现了电容",
               "v0.9 只验证过纯电阻负载的半波整流。"
               "电容滤波 / 峰值检波（二极管 + 电容）的波形和取数方式都还没验过，"
               "先去掉电容再仿真。")

    # v0.10.0 放开了"一个节点 2 个到地元件"，但**不含二极管电路**：
    # 二极管 + 并联负载的取数口径（哪个是负载电流、纹波怎么算）还没定。
    if any(len(s.shunts) > 1 for s in stages):
        reject("diode_parallel_load",
               "二极管电路里有一个节点挂了 %d 个到地元件"
               % max(len(s.shunts) for s in stages),
               "v0.10.0 的并联到地只放开给线性元件（电阻 / 电容 / 电源）。"
               "二极管 + 并联负载的测量口径还没定，先改成单个负载电阻。")

    if kind != "halfwave_rectifier":
        reject("diode_template_unverified",
               "带二极管的电路被判定为 %r，不是已验证的半波整流模板" % kind,
               "v0.9 只放开一种二极管拓扑：V1 -> D1 -> R1 -> GND。"
               "要求：1 个电源、1 个二极管（串在电源正极之后）、"
               "1 个电阻到地、1 个 GROUND。")

    if not series or series[0] != ds[0]:
        reject("diode_not_first_series",
               "二极管 %s 不在电源正极之后的第一个串联位" % ds[0],
               "把二极管直接接在电源正极上（D1.A 接源正极，D1.K 接负载）。")

    if len(shunts) != 1 or not _is_resistor(ir.component(shunts[0].shunt)):
        reject("diode_load_not_resistor",
               "二极管的负载不是单个电阻到地",
               "v0.9 只验证过电阻负载。接电容、接电感、接别的子电路都还没验过。")


def _classify(ir, stages):
    """按"串联数 + 到地数 + 元件类型"给出模板名。"""
    n_series = len(stages) - 1
    shunts = [s for s in stages if s.shunt]

    # v0.10.0：同一节点挂 2 个到地元件 —— 先判它。
    # 排在 shunt_load / divider 之前，否则"电源 + 两个并联电阻"会被叫成
    # shunt_load，"分压器 + 旁路电容"会被叫成 divider，名字错了后面全跟着错。
    if any(len(s.shunts) > 1 for s in stages):
        return "parallel_shunt"

    if n_series == 0:
        return "shunt_load"
    if not shunts:
        return "series_chain"
    if n_series == 1 and len(shunts) == 1:
        # 二极管 + 电阻：半波整流。必须排在 divider 之前判 —— 否则会被
        # 当成"电阻分压"（因为到地的那个是电阻），名字错了后面全跟着错。
        # 二极管 + 电容（峰值检波）刻意**不**归到这里：它没验过，
        # 交给 _check_diode_topology 报 diode_with_capacitor。
        if (_is_diode(ir.component(stages[0].series))
                and _is_resistor(ir.component(shunts[0].shunt))):
            return "halfwave_rectifier"
        comp = ir.component(shunts[0].shunt)
        return "divider" if _is_resistor(comp) else "bypass"
    if (n_series == 2 and len(shunts) == 1
            and shunts[0].index == 1
            and _is_resistor(ir.component(shunts[0].shunt))):
        return "tee"
    return "ladder"


# ---------------------------------------------------------------------------
# 第二步：坐标布局（不认识电路语义）
# ---------------------------------------------------------------------------
def _shunt_offset(j, k):
    """同一节点上第 j 个（共 k 个）到地元件相对本级列的水平偏移。

    k == 1 -> 0：和 v0.1~v0.9 算出来的坐标**完全一致**，一个字节都不变
               （已验收的 6 类拓扑坐标被真机测试固定住了，不能顺手改）。
    k == 2 -> ∓SHUNT_DX/2：以本级列为对称轴，左右各半格。
    """
    if k <= 1:
        return 0.0
    return (j - (k - 1) / 2.0) * SHUNT_DX


def plan(topology):
    """按拓扑给每个元件一个坐标。返回 {refdes: [x, y]}。

    有模板的拓扑走模板表；其余（v0.1~v0.8 验证过的 6 类）走下面这段通用规则 ——
    **两条路径算出来的坐标必须一致时才能合并，现在刻意不合并**，因为通用规则
    的输出已经被 3 次真机验收固定住了，不能顺手改。
    """
    tpl = KIND_TEMPLATES.get(topology.kind)
    if tpl is not None:
        return _plan_from_template(topology, tpl)

    pos = {topology.source: [X0, Y_MAIN],
           topology.ground: [X0, Y_GND]}
    for st in topology.stages:
        x = _col_x(st.index)
        if st.series:
            # 串联元件摆在"本级 -> 下一级"的中间，画出来是一段横线
            pos[st.series] = [x + DX / 2.0, Y_MAIN]
        for j, ref in enumerate(st.shunts):
            # 并联元件挂在本级正下方，画出来是一段竖线；
            # 有 2 个时左右各偏半格，同一行并排 —— "并联"一眼可见
            pos[ref] = [x + _shunt_offset(j, len(st.shunts)), Y_SHUNT]
    return pos


def _plan_from_template(topology, tpl):
    """按模板表算坐标（v0.9 起新增拓扑走这里）。"""
    sx, sy = tpl["series_offset"]
    hx, hy = tpl["shunt_offset"]
    pos = {topology.source: [X0, Y_MAIN],
           topology.ground: [X0, Y_GND]}
    for st in topology.stages:
        x = _col_x(st.index)
        if st.series:
            pos[st.series] = [x + DX * sx, Y_MAIN + sy]
        for j, ref in enumerate(st.shunts):
            pos[ref] = [x + DX * hx + _shunt_offset(j, len(st.shunts)),
                        Y_SHUNT + hy]
    return pos


def plan_ir(ir):
    """analyze + plan 一步到位，返回 (Topology, {refdes: [x, y]})。"""
    topo = analyze(ir)
    return topo, plan(topo)
