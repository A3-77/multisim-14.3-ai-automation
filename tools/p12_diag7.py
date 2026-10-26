# -*- coding: utf-8 -*-
"""P12 诊断8：R1-R2 分压器（无电容），探针放中点。

判别：
  2.5V -> 克隆电阻能导通，且探针能读中间节点  => RC 的锅在 C1
  0V   -> 克隆电阻开路（或探针读不了非源节点）
  5V   -> R1 被短路
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

OUT = os.path.join(ROOT, "out", "p12_divider.ms14")
SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")


def place(a, refdes, target, pin="1", donor=None, donor_ref=None, value=None):
    ciid, _ = a.add_part("X", "Y", refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor, donor_refdes=donor_ref)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    info = a.c.pin_info(ciid)
    print("  %-4s 引脚=%s" % (refdes, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                                       for k, v in info.items()}))
    return ciid, info


a = msbuild.Assembler()
d = msbuild.load_donor(SPICE)
gnds = [c for c in d.components() if c["part"] == "GROUND"]
d.set_refdes(gnds[0]["ciid"], "GNDA")
d.set_refdes(gnds[3]["ciid"], "GNDC")

v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref="V2", value=5.0)
r1, rinfo = place(a, "R1", (500.0, 300.0), donor=d, donor_ref="R1", value=1000.0)
r2, r2info = place(a, "R2", (650.0, 400.0), donor=d, donor_ref="R1", value=1000.0)
ga, _ = place(a, "0", (300.0, 420.0), donor=d, donor_ref="GNDA")
gc, _ = place(a, "0", (650.0, 500.0), donor=d, donor_ref="GNDC")

n1 = a.connect([(v1, "1"), (r1, "1")], name="in")
n2 = a.connect([(r1, "2"), (r2, "1")], name="mid")
a.connect([(r2, "2"), (gc, "1")], name="0")
a.connect([(v1, "2"), (ga, "1")], name="0")
print("节点 in=%s mid=%s" % (n1, n2))

p = (r2info["1"]["xy"][0], rinfo["2"]["xy"][1])
print("探针 mid 位置=%s" % (p,))
clone_probe_ext(a, PROBE_DONOR, *p)

n, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))
back = msmodel.Circuit.load(OUT)
for e in back.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        lnk = inner[0]
        print("  wire Node=%s pts=%s" % (lnk.get("Node"),
              [(x.get("X"), x.get("Y")) for x in lnk.find("Points")]))
