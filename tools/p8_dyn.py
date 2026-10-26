# -*- coding: utf-8 -*-
"""P8：验证「立即 stopped = 纯电阻电路瞬态瞬间完成」理论。

p7_isolate 是 V2(5V) + R1(1k) + GND 的纯电阻回路——没有任何动态元件，
瞬态仿真理论上瞬间完成（state 立刻回到 stopped，无错误）。
donor_spice / 7812 能长时间 running 是因为它们有 L/C 持续动态。

本实验：在 p7 回路上跨接一个 100µF 电容（tau = R*C = 0.1s），
让 5s 的瞬态仿真全程有动态。若 ever_running=true →
「自建电路不被仿真引擎接受」是误判，纯电阻回路本来就会瞬间跑完。

输出 out/p8_dyn.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402
import msbuild  # noqa: E402

BASE = os.path.join(ROOT, "out", "_p7_isolate.xml")
DONOR = os.path.join(ROOT, "out", "_donor_spice.xml")
OUT = os.path.join(ROOT, "out", "p8_dyn.ms14")

donor = msmodel.Circuit.from_xml_file(DONOR)
a = msbuild.Assembler(base_path=BASE)

ref2ciid = {c["refdes"]: c["ciid"] for c in a.c.components()}
V2 = ref2ciid["V2"]
print("p7 基底元件:", [c["refdes"] for c in a.c.components()])

# 克隆 donor 的 C1，设 100µF
dc = msbuild.Donor(donor, "C1")
c1, c1_ports = a.add(dc, x=430.0, y=360.0, refdes="C1")
a.c.set_value_by_refdes("C1", 1e-4)
print("C1 CiID=%s ports=%s（100µF）" % (c1, c1_ports))

# 跨接在 V2 两端（net1 与 net0 之间）
n_top = a.connect([(V2, "1"), (c1, "1")], name="5")
n_bot = a.connect([(V2, "2"), (c1, "2")], name="6")
print("C 上端节点=%s 下端节点=%s" % (n_top, n_bot))

a.save(OUT)
print("写出 %s" % OUT)

back = msmodel.Circuit.load(OUT)
print("回读:", back.summary())
