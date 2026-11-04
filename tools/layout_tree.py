# -*- coding: utf-8 -*-
"""分叉树布局（v0.11.0）：一个节点有 2 条以上向下的主干。

为什么单独一个模块
------------------
`layout.py` 的 `analyze()` 走的是**单主干**模型：从电源正极出发，一路向下
直到地，每个节点只能有一条"往下的主干"。这个模型被 v0.1~v0.10 的 6 次真机
验收固定住了，坐标一个字节都不能动。

分叉是另一个模型：一个节点可以分出 2 条（或更多）支路，各自往下走，最后都
回到同一个地。**它不该被塞进单主干循环里** —— 那样要么改动老路径的坐标，
要么让老路径的代码长出一堆 `if fork` 分支。所以这里独立成模块，由
`layout.analyze()` 在检测到分叉时整棵树交过来。

几何：树往下长，支路并排
------------------------
v0.11.0 第一版把支路画成**水平泳道**，真机直接失败 —— 因为 Multisim 的
电阻/电容 donor 是**竖直符号**（引脚在上下，中心 ±22.5），不是水平的。
水平泳道会让"两个元件之间的导线"变成一条水平直线，没有拐点，探针只能落在
引脚上，结果 3 个探针只注册上 2 个。

现在的画法顺着符号本身的朝向：

            V1 ──┬──────────┬
                 R1         R2
                 │          │
                 C1         C2
                 │          │
                 └────┬─────┘
                     GND

* **向下 = 深度**（y = Y_TOP + 2·STEP·depth）
* **向右 = 支路**（同层支路按子树宽度分列，列距 COL）
* 节点（网络）本身没有符号，是一条水平接线
* 地放在最下方居中，所有到地元件沿竖线下来再横向汇合

走线为什么必须由布局器指定
--------------------------
两个引脚之间的 L 形折线（`wire` 的 "hv"/"vh"）在这里不够用：

* 源要同时连到左右两条支路，而**源符号自己挡在中间**，任何 L 形都会穿过它；
* 分叉节点的几条支路要汇到同一条水平线上，L 形会把竖线压在兄弟支路的引脚上。

所以这里给每条网络算出**折点**（`wiring_hints`），由 `wire_via` 画。
折点的首尾不用管：`wire_via` 用实际引脚坐标，布局器只给中间几个拐点。

还有一个坑：两点直线（比如"串联元件下引脚 -> 到地元件上引脚"，同一条竖线）
没有中间顶点，探针无处可落。`wiring_hints` 给这类网络打 `tap=True`，
编译时在正中插一个共线折点 —— 看起来还是直线，但探针有地方放了。
"""
import layout as L


# 支路之间的列距。元件符号宽约 40，240 让两条支路之间留出能看清的空白。
COL = 240.0

# 一个元件占的垂直高度（元件中心 -> 下一个节点）。
# 元件引脚在中心上下 22.5，所以 110 意味着相邻元件之间还有 65 的空隙。
STEP = 110.0

# 第一层节点的 y。
Y_TOP = 200.0

# 地符号相对最深层再往下的距离。
GND_DY = 130.0

# 树深上限（根为 0）。不是做不到，是没验过。
MAX_DEPTH = 4

# 单个节点的支路上限。
MAX_BRANCHES = 4

# 整棵树的元件数上限（含到地）。
MAX_ELEMENTS = 24

# 元件引脚相对符号中心的垂直偏移（电阻 / 电容 / 虚拟源都是 ±22.5 或 ±27，
# 取 22.5 只用于算折点的 y，最终首尾由 wire_via 用真实引脚坐标覆盖）。
PIN_DY = 22.5


class Branch(object):
    """从某个节点出发的一条支路。

    `series`   这条支路上的元件位号
    `from_pin` 元件接**父节点**的那个引脚名（几何上朝上）
    `to_pin`   元件接子节点 / 地的那个引脚名（几何上朝下）
    `to_net`   另一端的网络（到地支路就是地网）
    `kind`     "series"（还有下一级）或 "shunt"（直接到地）
    `child`    下一级节点；到地支路为 None
    `x`, `y`   元件符号中心的坐标
    """

    __slots__ = ("series", "from_pin", "to_pin", "to_net", "kind", "child",
                 "x", "y", "cols")

    def __init__(self, series, from_pin, to_pin, to_net, kind="series"):
        self.series = series
        self.from_pin = from_pin
        self.to_pin = to_pin
        self.to_net = to_net
        self.kind = kind
        self.child = None
        self.x = 0.0
        self.y = 0.0
        self.cols = 1

    def to_dict(self):
        return {"series": self.series, "from_pin": self.from_pin,
                "to_pin": self.to_pin, "to_net": self.to_net,
                "kind": self.kind, "x": self.x, "y": self.y,
                "child": self.child.to_dict() if self.child else None}

    def __repr__(self):
        return "Branch(%r, %s, x=%.0f, y=%.0f)" % (
            self.series, self.kind, self.x, self.y)


class TreeNode(object):
    """树上的一个节点 = 一条网络。

    `parent_ref` 是**进入**这个节点的元件（根节点为 None，代表从源正极进来）。
    走线时用它当"星型中心"：几条支路都连到它的下引脚上。
    """

    __slots__ = ("net", "depth", "branches", "x", "y", "cols", "parent_ref")

    def __init__(self, net, depth, parent_ref=None):
        self.net = net
        self.depth = depth
        self.branches = []
        self.x = 0.0
        self.y = 0.0
        self.cols = 1
        self.parent_ref = parent_ref

    @property
    def series(self):
        return [b.series for b in self.branches if b.kind == "series"]

    @property
    def shunts(self):
        return [b.series for b in self.branches if b.kind == "shunt"]

    def to_dict(self):
        return {"net": self.net, "depth": self.depth,
                "x": self.x, "y": self.y, "parent_ref": self.parent_ref,
                "branches": [b.to_dict() for b in self.branches]}

    def __repr__(self):
        return "TreeNode(%r, depth=%d, %d 条支路)" % (
            self.net, self.depth, len(self.branches))


class TreeTopology(object):
    """`analyze_tree()` 的产物。

    和 `layout.Topology` 保持**同名属性**（kind / source / ground / in_net /
    gnd_net / out_net / n_series / n_shunt / to_dict / summary），这样会话层、
    MCP 层、测试都不需要为"树"写第二套分支。区别只在多出来的 `root` / `nodes`
    / `paths` / `forks`。
    """

    def __init__(self, root, source, ground, in_net, gnd_net, kind):
        self.root = root
        self.source = source
        self.ground = ground
        self.in_net = in_net
        self.gnd_net = gnd_net
        self.kind = kind
        self.out_net = root.net
        self.nodes = []
        # 地符号的 y（plan_tree 填）。走线提示要用它算"到地支路往下走多远"。
        self.ground_y = None
        _flatten(root, self.nodes)

    # ---------- 统计 ----------
    @property
    def n_series(self):
        return sum(1 for n in self.nodes for b in n.branches
                   if b.kind == "series")

    @property
    def n_shunt(self):
        return sum(1 for n in self.nodes for b in n.branches
                   if b.kind == "shunt")

    @property
    def elements(self):
        return [b.series for n in self.nodes for b in n.branches]

    @property
    def depth(self):
        return max(n.depth for n in self.nodes)

    def paths(self):
        """所有"从根到地"的通路，每条是元件位号列表。"""
        out = []

        def walk(node, acc):
            for b in node.branches:
                if b.child is None:
                    out.append(acc + [b.series])
                else:
                    walk(b.child, acc + [b.series])

        walk(self.root, [])
        return out

    def forks(self):
        """分叉点：[{net, branches}]，只列真的分出 ≥2 条串联支路的节点。"""
        return [{"net": n.net, "branches": n.series}
                for n in self.nodes if len(n.series) > 1]

    # ---------- 输出 ----------
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
            # 树形拓扑没有"级"的概念，stages 给空列表；
            # 结构信息在 tree / paths / forks 里，别让调用方误读 stages。
            "stages": [],
            "tree": self.root.to_dict(),
            "paths": self.paths(),
            "forks": self.forks(),
            "depth": self.depth,
        }

    def summary(self):
        lines = ["拓扑 %s：%d 条通路 / %d 个串联 / %d 个到地（树深 %d）"
                 % (self.kind, len(self.paths()), self.n_series,
                    self.n_shunt, self.depth),
                 "  %s(+) -> %s" % (self.source, self.in_net)]
        for p in self.paths():
            lines.append("  " + " -> ".join(p) + " -> %s" % self.gnd_net)
        return "\n".join(lines)


def _flatten(node, out):
    """按深度优先把节点摊平（父在前、子在后）。"""
    out.append(node)
    for b in node.branches:
        if b.child is not None:
            _flatten(b.child, out)


# ---------------------------------------------------------------------------
# 第一步：建树（不认识坐标）
# ---------------------------------------------------------------------------
def analyze_tree(ir, src, gnd, in_net, gnd_net):
    """把分叉电路解析成 `TreeTopology`。不支持的形状抛 `LayoutError`。

    调用前提：`layout.analyze()` 已经做完单电源 / 单地 / 电源负极接地这些
    前置检查，并把 `src` / `gnd` / `in_net` / `gnd_net` 算好了。
    """
    ds = [c.refdes for c in ir.components if c.family == "DIODE"]
    if ds:
        raise L._unsupported(
            "diode_with_fork",
            "二极管电路里出现了分叉（%s）" % ", ".join(ds),
            "v0.9 只验证过单支路的半波整流。二极管 + 并联支路（全波 / 桥式 / "
            "双负载）还没验过，先去掉分叉。",
            diodes=ds)

    visited = {src.refdes, gnd.refdes}
    path = []

    def walk(net, depth, parent_ref):
        if net in path:
            raise L._unsupported(
                "cycle", "拓扑回到了已经走过的节点 %r，有环路" % net,
                "反馈 / 环路还没验证过。把反馈断开，或先只验前向通路。",
                net=net)
        if depth > MAX_DEPTH:
            raise L._unsupported(
                "too_deep",
                "支路嵌套到第 %d 层，超过验证上限 %d 层" % (depth, MAX_DEPTH),
                "不是做不到，是超过 %d 层的树形排布没实测过。"
                "先拆成子电路分别验。" % MAX_DEPTH,
                depth=depth, limit=MAX_DEPTH)

        node = TreeNode(net, depth, parent_ref)
        path.append(net)

        for ref, pin in ir.net(net).refs():
            if ref in (src.refdes, gnd.refdes):
                continue                    # 源和地不是支路
            if ref in visited:
                if ref == parent_ref:
                    continue                # 回到父节点的那一端，正常
                raise L._unsupported(
                    "cross_link",
                    "元件 %s 同时接在两条支路上（跨接）" % ref,
                    "树布局只支持「从电源出发一路向下、互不跨接」的支路。"
                    "跨接（旁路到另一条支路、桥接、反馈）还没验过。",
                    refdes=ref)
            comp = ir.component(ref)
            if comp is None:
                raise L.LayoutError(
                    "INTERNAL", "网络 %r 引用了不存在的元件 %r" % (net, ref))
            other = L._two_pin_other(comp, pin)
            if other is None:
                raise L._unsupported(
                    "non_two_pin",
                    "网络 %r 上的 %s 不是两端元件（%s/%s）"
                    % (net, ref, comp.family, comp.part),
                    "树布局只认两端元件：电阻、电容、电源、地。"
                    "多引脚元件（运放 / 555）走另一条布局路径。",
                    net=net, refdes=ref)
            onet = L._pin_net(ir, ref, other)
            if onet is None:
                raise L._unsupported(
                    "open_pin",
                    "%s 的另一个引脚（%s.%s）还没接线" % (ref, ref, other),
                    "布局要求每个元件的两端都接到网络。",
                    net=net, refdes=ref)

            visited.add(ref)
            node.branches.append(
                Branch(ref, pin, other, onet,
                       "shunt" if onet == gnd_net else "series"))

        if not node.branches:
            raise L._unsupported(
                "dead_end",
                "网络 %r 上没有任何元件可以往下走" % net,
                "这个节点既没有到地元件也没有向下的支路，电路是断的。"
                "把它接到地上，或删掉。",
                net=net)
        shunts = [b.series for b in node.branches if b.kind == "shunt"]
        if len(shunts) > L.MAX_SHUNTS_PER_NODE:
            # 和单主干同一个上限：2 个并联到地验过，3 个没验过。
            # 树布局在几何上其实能排 3 列，但"没验过"就是没验过。
            raise L._unsupported(
                "parallel_shunt",
                "网络 %r 有 %d 个到地元件（%s），超过上限 %d 个"
                % (net, len(shunts), ", ".join(shunts),
                   L.MAX_SHUNTS_PER_NODE),
                "一个节点上最多挂 %d 个到地元件。先把其中几个合并成一个"
                "等效元件，或拆成两个电路分别验。" % L.MAX_SHUNTS_PER_NODE,
                net=net, shunts=shunts, limit=L.MAX_SHUNTS_PER_NODE)
        if len(node.branches) > MAX_BRANCHES:
            raise L._unsupported(
                "too_many_branches",
                "网络 %r 分出了 %d 条支路，超过验证上限 %d 条"
                % (net, len(node.branches), MAX_BRANCHES),
                "不是做不到，是 %d 条以上并排时的排布没实测过。"
                "先把几条支路合并成一个等效元件。" % MAX_BRANCHES,
                net=net, branches=[b.series for b in node.branches],
                limit=MAX_BRANCHES)

        for b in node.branches:
            if b.kind == "series":
                b.child = walk(b.to_net, depth + 1, b.series)

        path.pop()
        return node

    root = walk(in_net, 0, None)

    leftover = [c.refdes for c in ir.components if c.refdes not in visited]
    if leftover:
        raise L._unsupported(
            "island",
            "这些元件和电源不连通（%s）" % ", ".join(leftover),
            "树布局只支持从电源正极一路走到地的连通拓扑。悬空元件、"
            "独立子电路都还不支持。",
            components=leftover)

    if len(visited) - 2 > MAX_ELEMENTS:
        raise L._unsupported(
            "too_many_elements",
            "电路有 %d 个元件，超过验证上限 %d 个"
            % (len(visited) - 2, MAX_ELEMENTS),
            "同上：不是做不到，是没验过。",
            count=len(visited) - 2, limit=MAX_ELEMENTS)

    return TreeTopology(root=root, source=src.refdes, ground=gnd.refdes,
                        in_net=in_net, gnd_net=gnd_net,
                        kind=_classify_tree(root))


def _classify_tree(root):
    """按"分叉点的形状"给模板名。

    parallel_branch  只有一个分叉点、正好 2 条支路（两组并联 / 两组 RC）
    fork_tree        其余（多层分叉、3 条以上支路）

    分成两个名字不是为了好看：`parallel_branch` 是这一版**真机验收过**的
    形状，`fork_tree` 只是"算法上能排、还没上过真机"的兜底。
    """
    forks = []
    for n in _iter_nodes(root):
        k = len(n.series)
        if k > 1:
            forks.append(k)
    if len(forks) == 1 and forks[0] == 2:
        return "parallel_branch"
    return "fork_tree"


def _iter_nodes(root):
    out = []
    _flatten(root, out)
    return out


# ---------------------------------------------------------------------------
# 第二步：坐标（不认识电路语义）
# ---------------------------------------------------------------------------
def _width(node):
    """后序算每棵子树占几列：每个到地支路（或叶）占 1 列。"""
    if not node.branches:
        node.cols = 1
        return 1
    total = 0
    for b in node.branches:
        w = _width(b.child) if b.child is not None else 1
        b.cols = w
        total += w
    node.cols = total
    return total


def _place(node, x_left, y):
    """前序把列号和层号翻译成坐标。"""
    node.x = x_left + (node.cols - 1) * COL / 2.0
    node.y = y
    cursor = x_left
    for b in node.branches:
        b.x = cursor + (b.cols - 1) * COL / 2.0
        b.y = y + STEP
        if b.child is not None:
            _place(b.child, cursor, y + 2.0 * STEP)
        cursor += b.cols * COL


def _deepest(node):
    """最靠下的 y（到地元件比节点再低一格）。"""
    low = node.y
    for b in node.branches:
        if b.child is not None:
            low = max(low, _deepest(b.child))
        else:
            low = max(low, b.y)
    return low


def plan_tree(topo):
    """按树拓扑给每个元件坐标。返回 {refdes: [x, y]}。"""
    _width(topo.root)
    _place(topo.root, L.X0, Y_TOP)

    pos = {}
    for n in _iter_nodes(topo.root):
        for b in n.branches:
            pos[b.series] = [b.x, b.y]

    # 源放在根的左边同一行：一眼能看出"从这里分出去"
    pos[topo.source] = [topo.root.x - COL, topo.root.y]
    # 地放在最下方、和根同一列：所有到地支路沿竖线下来再横向汇合
    topo.ground_y = _deepest(topo.root) + GND_DY
    pos[topo.ground] = [topo.root.x, topo.ground_y]
    return pos


def _pin_token(refdes, pin):
    return "%s.%s" % (refdes, pin)


def wiring_hints(topo):
    """给每条网络算出走线方案：{net_name: {...}}。

    每个 hint 可能是：

        {"tap": True}                       两点直线，请在中点插一个共线折点
        {"star": 引脚, "routes": {...}}      星型 + 折点（分叉节点）
        {"tap": True, "star": ...}          两者都要

    为什么"两点直线"要单独打标记：`net_vertices()` 对一条直线只返回两个端点，
    而探针只能落在顶点上 —— 于是探针被迫落在元件引脚上，真机实测会**丢通道**。
    在正中插一个共线折点后顶点变成 3 个，探针有地方落，看起来仍是直线。
    """
    hints = {}
    gnd_y = topo.ground_y

    for node in _iter_nodes(topo.root):
        # ---- 星型中心：进入这个节点的元件（根节点用源正极）----
        if node.parent_ref:
            hub = _pin_token(node.parent_ref, _to_pin_of(topo, node.parent_ref))
        else:
            hub = _pin_token(topo.source, "1")

        if len(node.branches) <= 1:
            # 单支路：L 形就够，只需要防"两点直线"
            hints[node.net] = {"tap": True}
            continue

        routes = {}
        for b in node.branches:
            # 折点：先沿元件自己的列竖到本节点那一行，再横到中心列
            routes[_pin_token(b.series, b.from_pin)] = [
                [b.x, node.y], [node.x, node.y]]
        hints[node.net] = {"star": hub, "routes": routes, "tap": False}

    # ---- 地网：所有到地支路沿竖线下来，横向汇到地符号 ----
    gnd_routes = {}
    for node in _iter_nodes(topo.root):
        for b in node.branches:
            if b.kind == "shunt":
                gnd_routes[_pin_token(b.series, b.to_pin)] = [
                    [b.x, gnd_y]]
    if gnd_routes:
        hints[topo.gnd_net] = {"star": _pin_token(topo.ground, "1"),
                               "routes": gnd_routes, "tap": False}
    return hints


def _to_pin_of(topo, refdes):
    """某个元件接"下游"的那个引脚名（布局器几何上朝下的那端）。"""
    for n in _iter_nodes(topo.root):
        for b in n.branches:
            if b.series == refdes:
                return b.to_pin
    return "2"
