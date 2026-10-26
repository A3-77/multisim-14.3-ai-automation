# -*- coding: utf-8 -*-
"""P18: 验证「结点缺失」假设 —— 搭一条所有网络都只有 2 个引脚的串联链。

假设：分压器中点恒 0V 的真正原因是**没有生成 junction（交汇结点）**。
     中点有 3 个引脚汇聚（R1.2 / R2.1 / C1.1），官方文件里这种 T 型交汇必须
     有一个 CODPinComp 结点对象，其 ConnectList 收集三根导线的端点令牌。
     我们的生成器从不创建结点 → 3 引脚以上的网全部断开。

本实验：V1(5V) - R1(1k) - C1(1µF) - R2(1k) - GND 串联链
     每个网恰好 2 个引脚，完全不需要结点。
     直流稳态：无电流 → node2(探针) = 5V，node3 = 0V。
     瞬态：node2 从 0 充到 5V，tau = C1*(R1+R2) = 2ms。

预期：若 node2 从 0 升到 5V → 2 引脚网工作正常 → 结点假设成立。
      若 node2 恒 0 → 假设被否，问题更底层。

产物: out/p18_series.ms14
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
OUT = os.path.join(ROOT, "out", "p18_series.ms14")

a = msbuild.Assembler()
d = msbuild.load_donor(SPICE)
gnds = [c for c in d.components() if c["part"] == "GROUND"]
d.set_refdes(gnds[0]["ciid"], "GNDA")

v1, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)
r1, _ = a.add(msbuild.Donor(d, "R1"), x=480.0, y=340.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)
c1, _ = a.add(msbuild.Donor(d, "C1"), x=640.0, y=340.0, refdes="C1")
a.c.set_value_by_refdes("C1", 1e-6)
r2, _ = a.add(msbuild.Donor(d, "R1"), x=800.0, y=340.0, refdes="R2")
a.c.set_value_by_refdes("R2", 1000.0)
g1, _ = a.add(msbuild.Donor(d, "GNDA"), x=800.0, y=470.0, refdes="0")

for tag, cid in (("V1", v1), ("R1", r1), ("C1", c1), ("R2", r2), ("GND", g1)):
    print("%-3s %s" % (tag, a.c.pin_info(cid)))

# 串联：V1.1 - R1.1 | R1.2 - C1.1 | C1.2 - R2.1 | R2.2 - GND | V1.2 - GND
n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n2 = a.connect([(r1, "2"), (c1, "1")], name="2")
n3 = a.connect([(c1, "2"), (r2, "1")], name="3")
a.connect([(r2, "2"), (g1, "1")], name="0")
a.connect([(v1, "2"), (g1, "1")], name="0")
print("节点: n1=%s n2=%s n3=%s" % (n1, n2, n3))

# 探针放在 n2 导线的拐点上
pts = None
wid = None
for e in a.objs:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == n2:
        wid = e.get("ID")
        pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
        break
print("n2 导线 %s pts=%s" % (wid, pts))
vx = pts[1] if len(pts) >= 3 else (pts[0] if pts else None)
print("探针落点 %s" % (vx,))
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
