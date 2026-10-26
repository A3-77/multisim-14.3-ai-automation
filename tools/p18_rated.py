# -*- coding: utf-8 -*-
"""P18: 换元件类 —— 用 RESISTOR_RATED（教学/工程文件用的那类）代替 RESISTOR_VIRTUAL。

对比对象：out/p18_divdc.ms14（RESISTOR_VIRTUAL，dc_op = 0V，应 2.5V）
本实验：  同拓扑，R1/R2 改为从 "02 同相加法器.ms14" 克隆的 RESISTOR_RATED

判读：2.5V → 元件类（RESISTOR_VIRTUAL）是根因，换供体即可
      0V   → 元件类无关，问题在生成器

产物: out/p18_rated.ms14
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
ADD = os.path.join(D, "02 同相加法器.ms14")
OUT = os.path.join(ROOT, "out", "p18_rated.ms14")

d = msbuild.load_donor(ADD)
print("供体元件:", [(c["refdes"], c["part"]) for c in d.components()])
gnds = [c for c in d.components() if c["part"] == "GROUND"]
print("GND:", len(gnds))
if len(gnds) >= 2:
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[1]["ciid"], "GNDC")

a = msbuild.Assembler()
v1, _ = a.add(msbuild.Donor(d, "V1"), x=300.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)
r1, _ = a.add(msbuild.Donor(d, "R1"), x=500.0, y=340.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)
r2, _ = a.add(msbuild.Donor(d, "R2"), x=650.0, y=430.0, refdes="R2")
a.c.set_value_by_refdes("R2", 1000.0)
g1, _ = a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=470.0, refdes="0")
g2, _ = a.add(msbuild.Donor(d, "GNDC"), x=650.0, y=540.0, refdes="0")

for tag, cid in (("V1", v1), ("R1", r1), ("R2", r2)):
    print("%-3s %s" % (tag, {k: v["xy"] for k, v in a.c.pin_info(cid).items()}))

n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n2 = a.connect([(r1, "2"), (r2, "1")], name="2")
a.connect([(r2, "2"), (g2, "1")], name="0")
a.connect([(v1, "2"), (g1, "1")], name="0")
print("node1=%s node2=%s" % (n1, n2))

vx = None
for e in a.objs:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == n2:
        pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
        vx = pts[1] if len(pts) >= 3 else pts[0]
        print("node2 导线 pts=%s 探针落点=%s" % (pts, vx))
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
