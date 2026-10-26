# -*- coding: utf-8 -*-
"""P15: 用 a.add(donor, x, y) 直接定位重做分压器（不用 add_part(x=0)+translate）
布局：V1(5V) -- R1(1k) -- 中点 -- R2(1k) -- GND，C1(1pF) 跨中点，探针在中点导线顶点
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")
OUT = os.path.join(ROOT, "out", "p15_divider.ms14")

a = msbuild.Assembler()
d = msbuild.load_donor(SPICE)
gnds = [c for c in d.components() if c["part"] == "GROUND"]
print("donor GND:", [g["refdes"] for g in gnds])
d.set_refdes(gnds[0]["ciid"], "GNDA")
d.set_refdes(gnds[3]["ciid"], "GNDC")

v1, vp = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)
r1, r1p = a.add(msbuild.Donor(d, "R1"), x=500.0, y=340.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)
r2, r2p = a.add(msbuild.Donor(d, "R1"), x=650.0, y=430.0, refdes="R2")
a.c.set_value_by_refdes("R2", 1000.0)
c1, c1p = a.add(msbuild.Donor(d, "C1"), x=790.0, y=430.0, refdes="C1")
a.c.set_value_by_refdes("C1", 1e-12)

for tag, cid in (("V1", v1), ("R1", r1), ("R2", r2), ("C1", c1)):
    print("%-3s %s" % (tag, {k: v["xy"] for k, v in a.c.pin_info(cid).items()}))

n_in = a.connect([(v1, "1"), (r1, "1")], name="1")
n_mid = a.connect([(r1, "2"), (r2, "1"), (c1, "1")], name="2")
n0a = a.connect([(v1, "2"), (a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=430.0)[0], "1")], name="0")
n0b = a.connect([(r2, "2"), (a.add(msbuild.Donor(d, "GNDC"), x=650.0, y=520.0)[0], "1")], name="0")
n0c = a.connect([(c1, "2"), (a.add(msbuild.Donor(d, "GNDC"), x=790.0, y=520.0)[0], "1")], name="0")
print("节点 in=%s mid=%s" % (n_in, n_mid))

# 找中点网的导线，取它的中间顶点放探针
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

# 检查引脚定义坐标是否有重合
from collections import Counter
coords = []
for el in back.tree.iter("Item"):
    if el.get("Class") == "CODPinComp" and len(list(el)) > 0:
        dd = el.find("CODPinComp")
        if dd is not None:
            coords.append((dd.get("CenterX"), dd.get("CenterY")))
cnt = Counter(coords)
print("引脚定义坐标:", coords)
print("重合坐标:", {k: v for k, v in cnt.items() if v > 1})
