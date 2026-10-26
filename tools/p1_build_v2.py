# -*- coding: utf-8 -*-
"""P1：生成带老式探针的验收电路（v2，修复了 CiNode 属性）。

修复内容：Assembler.connect() 现在给 CiNode 填完整的 36 槽 Attributes
（之前是空的 <Attributes />，导致 Multisim 不认网络、探针注册不成 COM output）。

探针位置必须落在网络导线的**顶点**上：
    net1 导线顶点：(346,300) [V1 pin1]、(513,300)、(513,296) [R1 pin1]
    net0 导线顶点：(346,336)、(513,336)、(513,341)、(574,341)、(574,456) [GND pin1]

输出 out/p1_acceptance_v2.ms14（不动 out/ref/ 下的原文件）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402
import msbuild  # noqa: E402

OUT = os.path.join(ROOT, "out", "p1_acceptance_v2.ms14")

donor = msmodel.Circuit.from_xml_file(os.path.join(ROOT, "out", "ref", "blank_circuit.xml"))
donor_src = os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz")
import gzip
donor = msmodel.Circuit(gzip.open(donor_src, "rb").read())

a = msbuild.Assembler()

dv = msbuild.Donor(donor, "V2")
v1, v1_ports = a.add(dv, x=360.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)

dr = msbuild.Donor(donor, "R1")
r1, r1_ports = a.add(dr, x=520.0, y=300.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

gnd_ref = [c for c in donor.components() if c["part"] == "GROUND"][0]["refdes"]
dg = msbuild.Donor(donor, gnd_ref)
g1, g1_ports = a.add(dg, x=520.0, y=420.0)

n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n0 = a.connect([(v1, "2"), (r1, "2"), (g1, "1")], name="0")
print("节点: net1=%s net0=%s" % (n1, n0))

# 导线顶点（从 pin_info 拿，确保精确）
info = {cid: a.c.pin_info(cid) for cid in (v1, r1, g1)}
print("V1 引脚:", {k: v["xy"] for k, v in info[v1].items()})
print("R1 引脚:", {k: v["xy"] for k, v in info[r1].items()})
print("GND 引脚:", {k: v["xy"] for k, v in info[g1].items()})

# net1 顶点取 V1 的 1 脚；net0 顶点取 GND 的 1 脚
p1 = info[v1]["1"]["xy"]
p0 = info[g1]["1"]["xy"]
print("探针位置: net1 -> %s, net0 -> %s" % (p1, p0))

ci1, dr1 = a.add_probe("1", p1[0], p1[1], name="Probe1")
ci0, dr0 = a.add_probe("0", p0[0], p0[1], name="Probe2")
print("探针: Probe1 CiID=%s 绘图=%s ; Probe2 CiID=%s 绘图=%s" % (ci1, dr1, ci0, dr0))

n, body = a.save(OUT)
print("\n写出 %s（%d 字节）" % (OUT, n))

back = msmodel.Circuit.load(OUT)
print("回读:", back.summary())
print("导线:", len([e for e in back.objects
                    if list(e) and list(e)[0].get("Class") == "CIITLinkComp"]))
for e in back.elements:
    if e.get("Class") == "CiProbeComp":
        i = e.find("CiProbeComp")
        print("  探针 CiID=%s LocalName=%r" % (e.get("CiID"), i.get("LocalName")))
for e in back.elements:
    if e.get("Class") == "CiNode":
        at = e.find("CiNode/Attributes")
        print("  CiNode %s Attributes 槽数=%d" % (e.get("CiID"), len(list(at)) if at is not None else 0))
