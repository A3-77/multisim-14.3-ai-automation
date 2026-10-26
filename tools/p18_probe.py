# -*- coding: utf-8 -*-
"""P18: 判定探针绑定是否可信。

设计：两个独立电压源，各自撑一个网，全部网络都只有 2 个引脚（不需要 junction）。

    node1: V1(5V).1 + R1.1
    node2: V2(3V).1 + R1.2      ← 探针放这里，电压由 V2 硬定在 3V
    node0: V1.2 + V2.2

判读：
    读到 3V  → 探针绑定正确，之前的 0V 是真的（元件确实没进网表）
    读到 5V  → 探针绑到了「带电源的那个网」，与位置无关 → 所有 0V 读数作废
    读到 0V  → 探针绑到了地 → 同上

产物: out/p18_probe.ms14
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
OUT = os.path.join(ROOT, "out", "p18_probe.ms14")

a = msbuild.Assembler()
d = msbuild.load_donor(SPICE)
gnds = [c for c in d.components() if c["part"] == "GROUND"]
d.set_refdes(gnds[0]["ciid"], "GNDA")
d.set_refdes(gnds[3]["ciid"], "GNDC")

v1, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)
v2, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=460.0, refdes="V2")
a.c.set_value_by_refdes("V2", 3.0)
r1, _ = a.add(msbuild.Donor(d, "R1"), x=520.0, y=380.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

for tag, cid in (("V1", v1), ("V2", v2), ("R1", r1)):
    print("%-3s %s" % (tag, a.c.pin_info(cid)))

n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n2 = a.connect([(v2, "1"), (r1, "2")], name="2")
# 两个电源的负端各自接一个地（避免出现 3 引脚网）
g1, _ = a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=600.0, refdes="0")
g2, _ = a.add(msbuild.Donor(d, "GNDC"), x=520.0, y=600.0, refdes="0")
a.connect([(v1, "2"), (g1, "1")], name="0")
a.connect([(v2, "2"), (g2, "1")], name="0")
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
