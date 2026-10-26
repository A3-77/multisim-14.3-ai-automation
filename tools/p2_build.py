# -*- coding: utf-8 -*-
"""P2 反向搭建：以剥离后的 7812 为基底，装 acceptance 拓扑 + 老式探针。

基底：out/rev_base_stripped.xml（7812 删光元件、保留全部全局结构）
元件：SPICE Command Line 样例的 V2(DC_POWER) / R1(RESISTOR_VIRTUAL) / GROUND
拓扑：net1 = V1.1 - R1.1 ；net0 = V1.2 - R1.2 - GND.1
探针：Probe1 绑 net1，位置取 net1 导线顶点

输出 out/p2_reverse.ms14
"""
import gzip
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402
import msbuild  # noqa: E402

BASE = os.path.join(ROOT, "out", "rev_base_stripped.xml")
OUT = os.path.join(ROOT, "out", "p2_reverse.ms14")

donor_src = os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz")
donor = msmodel.Circuit(gzip.open(donor_src, "rb").read())

a = msbuild.Assembler(base_path=BASE)
print("基底元件:", [c["refdes"] for c in a.c.components()])
print("基底节点:", a.c.nodes())
print("基底 CiCircuit CiID:", a.circuit_ciid)

# ---- 装元件 ----
dv = msbuild.Donor(donor, "V2")
v1, v1_ports = a.add(dv, x=360.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)

dr = msbuild.Donor(donor, "R1")
r1, r1_ports = a.add(dr, x=520.0, y=300.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

gnd_ref = [c for c in donor.components() if c["part"] == "GROUND"][0]["refdes"]
dg = msbuild.Donor(donor, gnd_ref)
g1, g1_ports = a.add(dg, x=520.0, y=420.0)

print("\nV1 CiID=%s ports=%s" % (v1, v1_ports))
print("R1 CiID=%s ports=%s" % (r1, r1_ports))
print("GND CiID=%s ports=%s" % (g1, g1_ports))

# ---- 连线 ----
n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
n0 = a.connect([(v1, "2"), (r1, "2"), (g1, "1")], name="0")
print("\nnet1=%s net0=%s" % (n1, n0))

# ---- 引脚坐标（决定探针放哪）----
for tag, cid in (("V1", v1), ("R1", r1), ("GND", g1)):
    info = a.c.pin_info(cid)
    print("%-4s 引脚: %s" % (tag, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                                   for k, v in info.items()}))

# net1 导线顶点
p_v1_1 = a.c.pin_info(v1)["1"]["xy"]
p_r1_1 = a.c.pin_info(r1)["1"]["xy"]
print("\nnet1 导线: (%g,%g) -> (%g,%g)" % (p_v1_1 + p_r1_1))

# ---- 放探针（位置取 V1 的 1 脚 = net1 导线起点顶点）----
ci1, dr1 = a.add_probe("1", p_v1_1[0], p_v1_1[1], name="Probe1")
print("Probe1: CiID=%s 绘图ID=%s" % (ci1, dr1))

# ---- 保存 ----
n, body = a.save(OUT)
print("\n写出 %s（%d 字节）" % (OUT, n))

# ---- 回读自检 ----
back = msmodel.Circuit.load(OUT)
print("\n回读:", back.summary())
print("导线:", len([e for e in back.objects
                    if list(e) and list(e)[0].get("Class") == "CIITLinkComp"]))
for e in back.elements:
    if e.get("Class") == "CiProbeComp":
        i = e.find("CiProbeComp")
        print("探针 CiID=%s LocalName=%r SymCompID=%s Circuit=%s"
              % (e.get("CiID"), i.get("LocalName"), i.get("SymCompID"), i.get("Circuit")))
for e in back.elements:
    if e.get("Class") == "CiNode":
        at = e.find("CiNode/Attributes")
        print("CiNode %s(%s) Attributes 槽=%d"
              % (e.get("CiID"), (e.find("CiNode").get("LocalName") or ""),
                 len(list(at)) if at is not None else 0))
# 探针绘图对象
for e in back.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITProbeComponent":
        print("探针绘图: ID=%s NetName=%r M20/M21=%s/%s CiProbeComp=%s"
              % (e.get("ID"), inner[0].get("NetName"),
                 inner[0].get("Transformer-M20"), inner[0].get("Transformer-M21"),
                 inner[0].get("CiProbeComp")))
# Probes 注册
for e in back.elements:
    if e.get("Class") == "CiCircuit":
        pr = e.find("CiCircuit/Probes")
        print("Probes 注册:", [i.get("CiID") for i in pr] if pr is not None else None)
        break
