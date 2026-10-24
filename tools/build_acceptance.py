# -*- coding: utf-8 -*-
"""组装验收电路：5V 直流源 + 1kΩ 电阻 + 接地，并连线。

拓扑：
    node1: V1.1(+) --- R1.1
    node0: V1.2(-) --- R1.2 --- GND.1
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

DONOR = os.path.join(ROOT, "corpus", "samples",
                     "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz")

import gzip
donor = msmodel.Circuit(gzip.open(DONOR, "rb").read())
a = msbuild.Assembler()

# 1) 直流电压源 5V
dv = msbuild.Donor(donor, "V2")
v1, v1_ports = a.add(dv, x=360.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)

# 2) 1kΩ 电阻
dr = msbuild.Donor(donor, "R1")
r1, r1_ports = a.add(dr, x=520.0, y=300.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

# 3) 接地
gnd_ref = [c for c in donor.components() if c["part"] == "GROUND"][0]["refdes"]
dg = msbuild.Donor(donor, gnd_ref)
g1, g1_ports = a.add(dg, x=520.0, y=420.0)

print("V1", v1, v1_ports)
print("R1", r1, r1_ports)
print("GND", g1, g1_ports)

for tag, cid in (("V1", v1), ("R1", r1), ("GND", g1)):
    info = a.c.pin_info(cid)
    print(tag, "引脚坐标:", {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                            for k, v in info.items()})

# 4) 连线
n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n0 = a.connect([(v1, "2"), (r1, "2"), (g1, "1")], name="0")
print("节点", n1, n0)

out = os.path.join(ROOT, "out", "ref", "acceptance.ms14")
n, body = a.save(out)
print("写出 %s (%d 字节)" % (out, n))

back = msmodel.Circuit.load(out)
print("回读:", back.summary())
links = [e for e in back.objects if list(e) and list(e)[0].get("Class") == "CIITLinkComp"]
print("导线数:", len(links))
