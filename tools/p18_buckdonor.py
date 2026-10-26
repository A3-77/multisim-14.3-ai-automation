# -*- coding: utf-8 -*-
"""P18: 换供体重跑 t1 —— 用 buck.ms14（已证实能导通）当克隆源。

假设：donor_spice.ms14 这个供体本身是坏的（从未被验证过能仿真），
     所以从它克隆出来的 R/C 全是开路。只有 DC 电源还正常，
     因为 DC 电源的网表行不需要模型/值代入那么复杂。

若本实验的 t1 读出 5V → 供体是根因，生成器没问题。
若仍是 0V           → 生成器确实漏了东西。

产物: out/p18_t1buck.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

BUCK = os.path.join(ROOT, "corpus", "samples14", "buck.ms14")
OUT = os.path.join(ROOT, "out", "p18_t1buck.ms14")

d = msbuild.load_donor(BUCK)
print("buck 元件:", [(c["refdes"], c["part"]) for c in d.components()])

# buck 有多个 GND，refdes 都是 "0"；给两个改成唯一名便于选取
gnds = [c for c in d.components() if c["part"] == "GROUND"]
print("GND 数:", len(gnds))
if len(gnds) >= 2:
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[1]["ciid"], "GNDB")

a = msbuild.Assembler()

v1, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)

r1, _ = a.add(msbuild.Donor(d, "R1"), x=480.0, y=340.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

# buck 的电容是 CAP_ELECTROLIT（有极性），用 C2
cap_ref = "C2"
cap_val = 1e-4
c1, _ = a.add(msbuild.Donor(d, cap_ref), x=640.0, y=340.0, refdes="C1")
a.c.set_value_by_refdes("C1", cap_val)

g1, _ = a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=560.0, refdes="0")

for tag, cid in (("V1", v1), ("R1", r1), ("C1", c1), ("GND", g1)):
    print("%-3s %s" % (tag, a.c.pin_info(cid)))

n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n2 = a.connect([(r1, "2"), (c1, "1")], name="2")
a.connect([(c1, "2"), (g1, "1")], name="0")
a.connect([(v1, "2"), (g1, "1")], name="0")
print("节点 n1=%s n2=%s" % (n1, n2))

vx = None
for e in a.objs:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == n2:
        pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
        vx = pts[1] if len(pts) >= 3 else pts[0]
        print("n2 导线 pts=%s 探针落点=%s" % (pts, vx))
        break
clone_probe_ext(a, PROBE_DONOR, vx[0], vx[1])

n, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))

back = msmodel.Circuit.load(OUT)
print("回读:", back.summary())
