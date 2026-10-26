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
    analysis    目前只支持 "transient"
    start/stop  秒
    sample_rate 采样率 Hz（COM 侧 request_output 用）
    step        None 表示由求解器自适应；给了就当作期望步长记录下来

    IR 本身不跑仿真。仿真设置由 tools/ir_run.py 读取后交给验证脚本执行。
"""
import json
from dataclasses import dataclass, field, asdict

IR_VERSION = 1

# IR 层目前**已验证**的元件白名单。
# 加新元件必须先在 Multisim 里跑通仿真，不要凭"样例里有"就加进来。
SUPPORTED = {
    ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"): {"pins": ("1", "2"), "aliases": {"+": "1", "-": "2"}},
    ("RESISTOR", "RESISTOR_VIRTUAL"): {"pins": ("1", "2"), "aliases": {}},
    ("CAPACITOR", "CAPACITOR_VIRTUAL"): {"pins": ("1", "2"), "aliases": {}},
    ("POWER_SOURCES", "GROUND"): {"pins": ("1",), "aliases": {}},
}

ANALYSES = ("transient",)


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

    # ---------- 校验（阶段 4 填充）----------
    def validate(self):
        """返回错误字符串列表；空列表表示合法。"""
        return []
