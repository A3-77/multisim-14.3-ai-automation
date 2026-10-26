# -*- coding: utf-8 -*-
"""P15c: 把同一个分压器搭在 buck.ms14（原生电路）之上，检验基底是否是根因"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")
BUCK_XML = os.path.join(ROOT, "out", "_p14_buck.xml")
OUT = os.path.join(ROOT, "out", "p15_div_buckbase.ms14")

a = msbuild.Assembler(base_path=BUCK_XML)
d = msbuild.load_donor(SPICE)
gnds = [c for c in d.components() if c["part"] == "GROUND"]
d.set_refdes(gnds[0]["ciid"], "GNDA")
d.set_refdes(gnds[3]["ciid"], "GNDC")

v1, _ = a.add(msbuild.Donor(d, "V2"), x=1300.0, y=300.0, refdes="V9")
a.c.set_value_by_refdes("V9", 5.0)
r1, _ = a.add(msbuild.Donor(d, "R1"), x=1500.0, y=340.0, refdes="R9")
a.c.set_value_by_refdes("R9", 1000.0)
r2, _ = a.add(msbuild.Donor(d, "R1"), x=1650.0, y=430.0, refdes="R8")
a.c.set_value_by_refdes("R8", 1000.0)
c1, _ = a.add(msbuild.Donor(d, "C1"), x=1790.0, y=430.0, refdes="C9")
a.c.set_value_by_refdes("C9", 1e-12)

for tag, cid in (("V9", v1), ("R9", r1), ("R8", r2), ("C9", c1)):
    print("%-3s %s" % (tag, {k: v["xy"] for k, v in a.c.pin_info(cid).items()}))

n_in = a.connect([(v1, "1"), (r1, "1")], name="1")
n_mid = a.connect([(r1, "2"), (r2, "1"), (c1, "1")], name="2")
a.connect([(v1, "2"), (a.add(msbuild.Donor(d, "GNDA"), x=1300.0, y=430.0)[0], "1")], name="0")
a.connect([(r2, "2"), (a.add(msbuild.Donor(d, "GNDC"), x=1650.0, y=520.0)[0], "1")], name="0")
a.connect([(c1, "2"), (a.add(msbuild.Donor(d, "GNDC"), x=1790.0, y=520.0)[0], "1")], name="0")
print("节点 in=%s mid=%s" % (n_in, n_mid))

mid_vertex = None
for e in a.objs:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == n_mid:
        pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
        print("中点导线 %s pts=%s" % (e.get("ID"), pts))
        if len(pts) >= 2:
            mid_vertex = pts[1]
        break
if mid_vertex is None:
    raise SystemExit("找不到中点导线")

clone_probe_ext(a, PROBE_DONOR, mid_vertex[0], mid_vertex[1])
print("探针 @", mid_vertex)
n, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))
