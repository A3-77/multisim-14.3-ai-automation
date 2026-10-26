# -*- coding: utf-8 -*-
"""P18: 换供体重跑 t1 —— 用原生案例库文件当克隆源。

假设：donor_spice.ms14 这个供体本身是坏的（从未被验证能仿真），
     从它克隆出来的 R/C 全开路，只有 DC 电源还正常。

供体：
  Amplificador para resistencia de 1mOhm.ms14 → V1(DC) / R1(虚拟电阻) / GND×2
  De cuadrada a sin.ms14                     → C1(虚拟电容)

拓扑：V1(5V) - R1(1k) - C1(1µF) - GND，探针在 R1/C1 之间
期望：稳在 5V（电容充满后无电流，R 上无压降）

产物: out/p18_t1native.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

D = os.path.join(ROOT, "corpus", "samples14")
AMP = os.path.join(D, "Amplificador para resistencia de 1mOhm.ms14")
SQR = os.path.join(D, "De cuadrada a sin.ms14")
OUT = os.path.join(ROOT, "out", "p18_t1native.ms14")

da = msbuild.load_donor(AMP)
db = msbuild.load_donor(SQR)
print("A:", [(c["refdes"], c["part"]) for c in da.components()])
print("B:", [(c["refdes"], c["part"]) for c in db.components()])

gnds = [c for c in da.components() if c["part"] == "GROUND"]
print("A 的 GND:", [g["ciid"] for g in gnds])
da.set_refdes(gnds[0]["ciid"], "GNDA")
da.set_refdes(gnds[1]["ciid"], "GNDC")

a = msbuild.Assembler()

v1, _ = a.add(msbuild.Donor(da, "V1"), x=300.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)

r1, _ = a.add(msbuild.Donor(da, "R1"), x=480.0, y=340.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

c1, _ = a.add(msbuild.Donor(db, "C1"), x=640.0, y=340.0, refdes="C1")
a.c.set_value_by_refdes("C1", 1e-6)

g1, _ = a.add(msbuild.Donor(da, "GNDA"), x=300.0, y=560.0, refdes="0")
g2, _ = a.add(msbuild.Donor(da, "GNDC"), x=640.0, y=560.0, refdes="0")

for tag, cid in (("V1", v1), ("R1", r1), ("C1", c1), ("GND1", g1), ("GND2", g2)):
    print("%-4s %s" % (tag, a.c.pin_info(cid)))

n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n2 = a.connect([(r1, "2"), (c1, "1")], name="2")
a.connect([(c1, "2"), (g2, "1")], name="0")
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
pm = {p["ciid"]: p for p in back.ports()}
for nd in back.nodes():
    names = []
    for pid in nd["ports"]:
        p = pm.get(pid)
        if p:
            ref = next((x["refdes"] for x in back.components() if x["ciid"] == p["component"]), "?")
            names.append("%s.%s" % (ref, p["name"]))
    print("  node %-10s ports=%s" % (nd["ciid"], names))
