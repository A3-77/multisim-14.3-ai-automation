# -*- coding: utf-8 -*-
"""实验任务一 · 展示用电路图（显式布线）。

为什么不复用 hw_lab1.build()：
那个版本是给仿真用的，连线走自动 L 形路由，画出来有两处硬伤——
  1. 地网按引脚顺序串成链，链路高度落在 RB2 下端，而 V2 比它更低，
     于是"V2.2 -> RB2.2"这段竖直导线从 V2 符号中间穿过去，
     看上去像把交流源短路了；
  2. vb 网络按 [C1, Q1.B, RB1, RB2] 顺序连，多出一条回折的平行线。
电气上没错（CiNode 是对的），但交作业的图不能这么画。

这里按教科书习惯手工排布：电源轨在上、地母线在下、信号从左到右，
每个网络都用 wire_via 指定折点。元件参数与 ce_amp_p20.ms14 完全一致。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile          # noqa: E402
import hw_lab1             # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1")

# 元件坐标 = 引脚质心。引脚偏移见 hw_geom.py 的输出。
POS = {
    "V2":   [110.0, 390.0],    # AC_VOLTAGE  1=(0,-27) 2=(0,27)
    "C1":   [110.0, 300.0],    # CAP_ELECTROLIT 1=(0,-22.5) 2=(0,22.5)
    "RW":   [400.0, 90.0],     # RESISTOR    1=(0,-22.5) 2=(0,22.5)
    "RB1":  [400.0, 175.0],
    "RB2":  [400.0, 330.0],
    "Q1":   [620.0, 250.0],    # 2N2222A  B=(-18,0) C=(9,-36) E=(9,36)
    "RC":   [629.0, 150.0],
    "C2":   [760.0, 236.5],    # 1=(0,-22.5) -> 214, 2=(0,22.5) -> 259
    "RL":   [880.0, 300.0],
    "RE":   [629.0, 340.0],
    "CE":   [760.0, 340.0],
    "V1":   [980.0, 430.0],    # DC_POWER    1=(0,-18) 2=(0,18)
    "GND1": [1020.0, 480.0],   # GROUND      1=(0,0)
}

Y_VCC = 40.0       # 电源轨
Y_BASE = 250.0     # 基极母线
Y_GND = 480.0      # 地母线

# 整体缩放。Multisim 打开时的默认缩放不随文件走，而 Ctrl+滚轮在真机上会丢消息、
# 方向也不稳定；把图纸坐标整体缩一档，比反复调缩放可靠得多。
S = 0.88


def build():
    hw_lab1.allow_parts()
    ir = irmod.CircuitIR(name="sch1")

    def add(ref, fam, part, val=None, params=None):
        ir.components.append(irmod.Component(
            refdes=ref, family=fam, part=part, value=val,
            params=params or {},
            position=[POS[ref][0] * S, POS[ref][1] * S]))

    add("V1", "POWER_SOURCES", "DC_POWER", 12.0)
    add("V2", "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", None,
        {1: 0.010, 3: 0.0, 5: 1000.0, 7: 0.0})
    add("RW", "RESISTOR", "RESISTOR_VIRTUAL", 40000.0)   # 200kΩ 的 20%
    add("RB1", "RESISTOR", "RESISTOR_VIRTUAL", 10000.0)
    add("RB2", "RESISTOR", "RESISTOR_VIRTUAL", 10000.0)
    add("RC", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("RE", "RESISTOR", "RESISTOR_VIRTUAL", 1000.0)
    add("RL", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("C1", "CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL", 10e-6)
    add("C2", "CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL", 10e-6)
    add("CE", "CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL", 47e-6)
    add("Q1", "BJT_NPN", "2N2222A")
    add("GND1", "POWER_SOURCES", "GROUND")

    def net(name, pins, hub, routes):
        scaled = {k: [[p[0] * S, p[1] * S] for p in v]
                  for k, v in routes.items()}
        ir.nets.append(irmod.Net(name=name, pins=pins, route="hv",
                                 star=hub, routes=scaled))

    # +12V 轨：RW.1 为枢纽，其余先上到 y=Y_VCC 再横过去
    net("vcc", ["RW.1", "RC.1", "V1.1"], "RW.1",
        {"RC.1": [[629.0, Y_VCC], [400.0, Y_VCC]],
         "V1.1": [[980.0, Y_VCC], [400.0, Y_VCC]]})

    # 电位器下端 -> RB1
    net("n6", ["RW.2", "RB1.1"], "RW.2", {})

    # 基极母线：RB1 / RB2 / C1 都并到 Q1.B
    net("vb", ["Q1.B", "C1.1", "RB1.2", "RB2.1"], "Q1.B",
        {"C1.1": [[110.0, Y_BASE]],
         "RB1.2": [[400.0, Y_BASE]],
         "RB2.1": [[400.0, Y_BASE]]})

    # 集电极：RC 下端 - Q1.C - C2 上端
    net("vc", ["Q1.C", "RC.2", "C2.1"], "Q1.C", {})

    # 发射极：RE 直下，CE 从右侧并入
    net("ve", ["Q1.E", "RE.1", "CE.1"], "Q1.E",
        {"CE.1": [[760.0, 300.0], [629.0, 300.0]]})

    # 输出：C2 下端 -> RL 上端
    net("vo", ["C2.2", "RL.1"], "C2.2", {"RL.1": [[880.0, 259.0]]})

    # 输入：V2 上端 -> C1 下端（竖直直线）
    net("vi", ["V2.1", "C1.2"], "V2.1", {})

    # 地母线：所有接地点先下到 y=Y_GND，再并到 GND1
    net("0", ["GND1.1", "V2.2", "RB2.2", "RE.2", "CE.2", "RL.2", "V1.2"],
        "GND1.1",
        {"V2.2": [[110.0, Y_GND]],
         "RB2.2": [[400.0, Y_GND]],
         "RE.2": [[629.0, Y_GND]],
         "CE.2": [[760.0, Y_GND]],
         "RL.2": [[880.0, Y_GND]],
         "V1.2": [[980.0, Y_GND]]})

    ir.simulation.analysis = "transient"
    ir.simulation.start = 0.0
    ir.simulation.stop = 0.2
    ir.simulation.step = 5e-6
    ir.simulation.sample_rate = 200000.0
    return ir


if __name__ == "__main__":
    ms14 = os.path.join(OUT, "sch1_p20.ms14")
    rep = ir_compile.compile_ir(build(), ms14, verbose=False)
    print("编译 %d 字节 -> %s" % (rep["bytes"], ms14))
