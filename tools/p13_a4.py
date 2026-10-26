# -*- coding: utf-8 -*-
"""P13-A4：不放电阻，V1.1 直接接到 C1.1（导线带拐点），探针放拐点。

判别：
  5V -> 探针能读任意带拐点的网络 => A3 的 0V 只能是 R1 不导通
  0V -> 探针读不了非源节点（问题在探针，不在电阻）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

OUT = os.path.join(ROOT, "out", "p13_a4.ms14")
SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")


def place(a, refdes, target, pin="1", donor=None, donor_ref=None, value=None):
    ciid, _ = a.add_part("X", "Y", refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor, donor_refdes=donor_ref)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    return ciid, a.c.pin_info(ciid)


a = msbuild.Assembler()
d = msbuild.load_donor(SPICE)
gnds = [c for c in d.components() if c["part"] == "GROUND"]
d.set_refdes(gnds[0]["ciid"], "GNDA")
d.set_refdes(gnds[3]["ciid"], "GNDC")

v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref="V2", value=5.0)
c1, cinfo = place(a, "C1", (650.0, 385.0), donor=d, donor_ref="C1", value=1e-12)
ga, _ = place(a, "0", (300.0, 430.0), donor=d, donor_ref="GNDA")
gc, _ = place(a, "0", (650.0, 470.0), donor=d, donor_ref="GNDC")

# V1.1 -- C1.1 一根导线，拐点自动落在 (650,300)
n = a.connect([(v1, "1"), (c1, "1")], name="2")
a.connect([(v1, "2"), (ga, "1")], name="0")
a.connect([(c1, "2"), (gc, "1")], name="0")
print("节点:", n)
for e in a.objs:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        print("  wire Node=%s pts=%s" % (inner[0].get("Node"),
              [(p.get("X"), p.get("Y")) for p in inner[0].find("Points")]))

p = (650.0, 300.0)
clone_probe_ext(a, PROBE_DONOR, *p)
print("探针 @", p)
nbytes, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, nbytes))
back = msmodel.Circuit.load(OUT)
print("回读:", back.summary())
