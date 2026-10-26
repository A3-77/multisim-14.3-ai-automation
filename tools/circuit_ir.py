# -*- coding: utf-8 -*-
"""Circuit IR —— 电路中间表示层（纯数据，不依赖 Multisim）。

设计原则
--------
1. **不暴露底层实现**。IR 里没有 CiID、CiPort、CIITSymbolComp、Transformer-M20、
   CiaParamList 这些词。调用方只描述「有哪些元件、谁和谁连、探针放哪、怎么仿真」。
2. **可序列化**。整个 IR 能存成一个 JSON 文件，能读回来，能 diff。
3. **不含行为**。这一层只负责"描述电路"，怎么变成 .ms14 是 ir_compile 的事。

结构
----
    CircuitIR
      ├── components   [Component]     元件：refdes / family / part / value / params / position
      ├── nets         [Net]           连接：一条网络有哪些引脚（"R1.1" 这种）
      ├── probes       [Probe]         探针：refdes + 目标网络（或显式坐标）
      └── simulation   Simulation      仿真：分析类型 + 起止时间 + 采样率

引脚写法
--------
    "R1.1"   —— 位号 R1 的 1 号引脚
    "V1.+"   —— 源类元件的正极（IR 层别名，编译时映射到实际的 "1"）

为什么用「网络 → 引脚列表」而不是「引脚对 → 引脚对」：
    前者天然表达多引脚网络（3 个以上引脚交汇），不需要额外的结点对象；
    后者在 T 型交汇处会退化成多条冗余导线。

仿真块说明
----------
    analysis    "transient"（时域）或 "dc"（直流工作点，单点）
    start/stop  秒（仅 transient 用）
    sample_rate 采样率 Hz（COM 侧 request_output 用，仅 transient 用）
    step        None 表示由求解器自适应；给了就当作期望步长记录下来（仅 transient 用）

    analysis="dc" 时 start/stop/sample_rate/step 都不参与校验也不参与执行 ——
    静态电路没有时间维度。实测两条路给出的电压完全一致
    （out/dc/dc_result_transient.json vs out/dc/dc_result_dcop.json）。

    IR 本身不跑仿真。仿真设置由 tools/nl_run.py 读取后交给验证脚本执行。
"""
import json
import re
from dataclasses import dataclass, field, asdict

IR_VERSION = 1

# IR 层目前**已验证**的元件白名单。
# 加新元件必须先在 Multisim 里跑通仿真，不要凭"样例里有"就加进来。
SUPPORTED = {
    ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"): {"pins": ("1", "2"), "aliases": {"+": "1", "-": "2"}},
    ("POWER_SOURCES", "DC_POWER"): {"pins": ("1", "2"), "aliases": {"+": "1", "-": "2"}},
    ("RESISTOR", "RESISTOR_VIRTUAL"): {"pins": ("1", "2"), "aliases": {}},
    ("CAPACITOR", "CAPACITOR_VIRTUAL"): {"pins": ("1", "2"), "aliases": {}},
    ("POWER_SOURCES", "GROUND"): {"pins": ("1",), "aliases": {}},
}

ANALYSES = ("transient", "dc")

_REFDES_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _norm_pin(comp, pin):
    """把 IR 层引脚名归一化成实际引脚名；不认识返回 None。

    "V1.+" 里的 '+' 是 IR 层别名，归一化后是 '1'。
    归一化的意义：判重时必须按物理引脚来 —— "V1.+" 和 "V1.1" 是同一根引脚，
    如果不去别名，同一引脚接两条网络这种错误会漏掉。
    """
    spec = SUPPORTED.get((comp.family, comp.part))
    if spec is None:
        return None
    if pin in spec["pins"]:
        return pin
    return (spec.get("aliases") or {}).get(pin)


@dataclass
class Component:
    refdes: str
    family: str
    part: str
    value: float = None
    params: dict = field(default_factory=dict)     # {参数序号(int): 数值}
    position: list = None                          # [x, y]，含义=引脚质心

    def __post_init__(self):
        # JSON 里对象的键一定是字符串，读回来要转成 int，否则 set_params 会失效
        if self.params:
            self.params = {int(k): v for k, v in self.params.items()}


@dataclass
class Net:
    name: str
    pins: list = field(default_factory=list)       # ["V1.+", "R1.1"]

    def refs(self):
        """拆成 [(refdes, pin), ...]。"""
        out = []
        for p in self.pins:
            ref, _, pin = str(p).partition(".")
            out.append((ref, pin))
        return out


@dataclass
class Probe:
    refdes: str
    kind: str = "V"                 # 目前只有电压探针
    net: str = None                 # 目标网络名；编译器自动挑一个导线顶点
    at: list = None                 # 或者显式给 [x, y]（必须是导线顶点）

    def target(self):
        return ("net", self.net) if self.net else ("at", tuple(self.at or ()))


@dataclass
class Simulation:
    analysis: str = "transient"
    start: float = 0.0
    stop: float = 0.0
    step: float = None
    sample_rate: float = 200000.0


@dataclass
class CircuitIR:
    name: str = "untitled"
    components: list = field(default_factory=list)
    nets: list = field(default_factory=list)
    probes: list = field(default_factory=list)
    simulation: Simulation = field(default_factory=Simulation)
    version: int = IR_VERSION

    # ---------- 构造 ----------
    @classmethod
    def from_dict(cls, d):
        comps = [Component(**c) for c in d.get("components") or []]
        nets = [Net(**n) for n in d.get("nets") or []]
        probes = [Probe(**p) for p in d.get("probes") or []]
        sim = Simulation(**(d.get("simulation") or {}))
        return cls(name=d.get("name") or "untitled", components=comps, nets=nets,
                   probes=probes, simulation=sim,
                   version=int(d.get("version") or IR_VERSION))

    def to_dict(self):
        d = asdict(self)
        # params 的键在 JSON 里必须是字符串；读回来由 Component.__post_init__ 转回 int
        for c in d["components"]:
            if c.get("params"):
                c["params"] = {str(k): v for k, v in c["params"].items()}
        return d

    # ---------- 文件 ----------
    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")

    # ---------- 查询 ----------
    def component(self, refdes):
        for c in self.components:
            if c.refdes == refdes:
                return c
        return None

    def net(self, name):
        for n in self.nets:
            if n.name == name:
                return n
        return None

    def summary(self):
        lines = ["CircuitIR %r  (%d 元件 / %d 网络 / %d 探针)"
                 % (self.name, len(self.components), len(self.nets), len(self.probes))]
        for c in self.components:
            v = "" if c.value is None else " = %g" % c.value
            p = (" pos=%s" % (c.position,)) if c.position else ""
            lines.append("  %-6s %-22s %-20s%s%s"
                         % (c.refdes, c.family, c.part, v, p))
        for n in self.nets:
            lines.append("  net %-6s %s" % (n.name, ", ".join(n.pins)))
        for p in self.probes:
            lines.append("  probe %-4s -> %s" % (p.refdes, p.net or p.at))
        s = self.simulation
        lines.append("  sim: %s stop=%gs sr=%gHz"
                     % (s.analysis, s.stop, s.sample_rate))
        return "\n".join(lines)

    # ---------- 校验 ----------
    def validate(self):
        """返回错误字符串列表；空列表表示合法。

        检查项（全部在写 .ms14 之前完成）：
            * 版本号
            * refdes 非空、格式合法、元件之间唯一、与探针不重名
            * 元件 (family, part) 在已验证白名单里
            * position 是 [x, y]
            * 网络名非空且唯一；每条网络至少 2 个引脚
            * 引脚写法合法、引用的元件存在、引脚在该元件上存在
            * 同一个物理引脚不能同时属于两条网络（别名会先归一化再判重）
            * 探针 kind / 目标（net 与 at 二选一）/ 目标网络存在
            * 仿真参数（分析类型、起止、步长、采样率、采样点数）
        """
        errs = []
        if int(self.version) != IR_VERSION:
            errs.append("版本号 %r 不受支持（当前只认 %d）"
                        % (self.version, IR_VERSION))
        if not self.components:
            errs.append("电路里没有任何元件")

        # ---------- 元件 ----------
        comp_by_ref = {}
        for i, comp in enumerate(self.components):
            tag = comp.refdes or ("components[%d]" % i)
            if not comp.refdes:
                errs.append("%s: refdes 为空" % tag)
                continue
            if not _REFDES_RE.match(comp.refdes):
                errs.append("%s: refdes 只能由字母/数字/下划线组成，且不能以数字开头"
                            % tag)
            if comp.refdes in comp_by_ref:
                errs.append("%s: refdes 重复" % tag)
                continue
            comp_by_ref[comp.refdes] = comp

            key = (comp.family, comp.part)
            if key not in SUPPORTED:
                errs.append("%s: 元件 %s/%s 不在已验证白名单里（可用：%s）"
                            % (tag, comp.family, comp.part,
                               ", ".join("%s/%s" % k for k in SUPPORTED)))
                continue
            if comp.position is not None:
                if (not isinstance(comp.position, (list, tuple))
                        or len(comp.position) != 2):
                    errs.append("%s: position 必须是 [x, y]" % tag)
                else:
                    try:
                        float(comp.position[0])
                        float(comp.position[1])
                    except (TypeError, ValueError):
                        errs.append("%s: position 不是数字" % tag)
            if comp.params:
                for k in comp.params:
                    if not isinstance(k, int):
                        errs.append("%s: params 的键必须是整数（参数序号），拿到 %r"
                                    % (tag, k))

        # ---------- 网络 ----------
        net_names = set()
        pin_owner = {}          # 归一化后的 "REF.PIN" -> 网络名
        for i, net in enumerate(self.nets):
            tag = "net %r" % (net.name or ("nets[%d]" % i))
            if not net.name:
                errs.append("%s: 网络名为空" % tag)
            elif net.name in net_names:
                errs.append("%s: 网络名重复" % tag)
            else:
                net_names.add(net.name)

            if len(net.pins) < 2:
                errs.append("%s: 只有 %d 个引脚，至少要 2 个"
                            % (tag, len(net.pins)))

            for tok in net.pins:
                ref, sep, pin = str(tok).partition(".")
                if not sep or not ref or not pin:
                    errs.append("%s: 引脚写法不对 %r（应为 '位号.引脚'，如 'R1.1'）"
                                % (tag, tok))
                    continue
                comp = comp_by_ref.get(ref)
                if comp is None:
                    errs.append("%s: 引用了不存在的元件 %r" % (tag, ref))
                    continue
                spec = SUPPORTED.get((comp.family, comp.part))
                if spec is None:
                    continue        # 元件本身已经报过错，别重复
                norm = _norm_pin(comp, pin)
                if norm is None:
                    errs.append("%s: %s（%s/%s）没有引脚 %r，可用：%s"
                                % (tag, ref, comp.family, comp.part, pin,
                                   sorted(set(spec["pins"]) | set(spec["aliases"]))))
                    continue
                key = "%s.%s" % (ref, norm)
                if key in pin_owner:
                    errs.append("%s: 引脚 %s 已经属于网络 %r，不能再连到 %r"
                                % (tag, key, pin_owner[key], net.name))
                else:
                    pin_owner[key] = net.name

        # 完全没接线的元件（所有引脚都不在任何网络里）
        for ref, comp in comp_by_ref.items():
            spec = SUPPORTED.get((comp.family, comp.part))
            if spec is None:
                continue
            used = any("%s.%s" % (ref, p) in pin_owner for p in spec["pins"])
            if not used:
                errs.append("%s: 所有引脚都没有接线（孤立元件）" % ref)

        # ---------- 探针 ----------
        probe_refs = set()
        for i, pr in enumerate(self.probes):
            tag = pr.refdes or ("probes[%d]" % i)
            if not pr.refdes:
                errs.append("%s: refdes 为空" % tag)
            elif pr.refdes in comp_by_ref:
                errs.append("%s: 探针 refdes 与元件重名" % tag)
            elif pr.refdes in probe_refs:
                errs.append("%s: 探针 refdes 重复" % tag)
            else:
                probe_refs.add(pr.refdes)

            if pr.kind != "V":
                errs.append("%s: kind=%r 不支持（目前只有 'V'）" % (tag, pr.kind))
            if pr.net and pr.at:
                errs.append("%s: net 和 at 只能给一个" % tag)
            elif not pr.net and not pr.at:
                errs.append("%s: 必须给 net（目标网络）或 at（显式坐标）" % tag)
            elif pr.net and pr.net not in net_names:
                errs.append("%s: 目标网络 %r 不存在" % (tag, pr.net))
            elif pr.at:
                if (not isinstance(pr.at, (list, tuple)) or len(pr.at) != 2):
                    errs.append("%s: at 必须是 [x, y]" % tag)
                else:
                    try:
                        float(pr.at[0])
                        float(pr.at[1])
                    except (TypeError, ValueError):
                        errs.append("%s: at 不是数字" % tag)

        # ---------- 仿真 ----------
        s = self.simulation
        if s.analysis not in ANALYSES:
            errs.append("simulation.analysis=%r 不支持（可用：%s）"
                        % (s.analysis, ", ".join(ANALYSES)))
        if s.analysis == "dc":
            # 直流工作点是单点分析：没有时间窗口，stop / sample_rate / step 都不适用
            return errs
        try:
            start, stop = float(s.start or 0.0), float(s.stop or 0.0)
        except (TypeError, ValueError):
            errs.append("simulation.start / stop 不是数字")
        else:
            if start < 0:
                errs.append("simulation.start 不能为负（%g）" % start)
            if stop <= 0:
                errs.append("simulation.stop 必须大于 0（%g）" % stop)
            elif start >= stop:
                errs.append("simulation.start（%g）必须小于 stop（%g）"
                            % (start, stop))
            try:
                sr = float(s.sample_rate or 0.0)
            except (TypeError, ValueError):
                errs.append("simulation.sample_rate 不是数字")
            else:
                if sr <= 0:
                    errs.append("simulation.sample_rate 必须大于 0（%g）" % sr)
                elif stop > start:
                    npts = (stop - start) * sr
                    if npts < 100:
                        errs.append("采样点太少：(%g-%g)*%g = %.0f 点，至少要 100"
                                    % (stop, start, sr, npts))
            if s.step is not None:
                try:
                    step = float(s.step)
                except (TypeError, ValueError):
                    errs.append("simulation.step 不是数字")
                else:
                    if step <= 0:
                        errs.append("simulation.step 必须大于 0（%g）" % step)
                    elif stop > start and step > (stop - start):
                        errs.append("simulation.step（%g）比仿真窗口（%g）还大"
                                    % (step, stop - start))
        return errs

    def warnings(self):
        """不阻断生成、但值得提醒的问题。"""
        out = []
        if not any(c.part == "GROUND" for c in self.components):
            out.append("电路里没有 GROUND，SPICE 网表可能没有参考地")
        if not self.probes:
            out.append("没有任何探针，COM 侧将取不到任何输出")
        return out

