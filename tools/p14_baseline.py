# -*- coding: utf-8 -*-
"""P14-3：原装电阻基线 —— 不克隆 R1，直接在 donor_spice 里用它。

电路：V2.1(源) -- R1(原装 50Ω) -- 中点 -- C1(1pF) -- GND，探针在中点顶点。
若中点读到源电压 -> 原装 R1 导通，问题只在「克隆」；
若中点 0V      -> 原装 R1 也不导通，问题在别处（不是克隆的锅）。

产物：out/p14_baseline.ms14
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

BASE = os.path.join(ROOT, "out", "_donor_spice.xml")
OUT = os.path.join(ROOT, "out", "p14_baseline.ms14")

a = msbuild.Assembler(base_path=BASE)
c = a.c
print("基底元件:", [(x["refdes"], x["part"]) for x in c.components()])

v2 = c.find("V2")["ciid"]
r1 = c.find("R1")["ciid"]
print("V2=%s R1=%s" % (v2, r1))
print("V2 参数:", c.params(c.find("V2")["comp"])[:2], " R1 参数:", c.params(c.find("R1")["comp"])[:2])
print("R1 引脚:", {k: v["xy"] for k, v in c.pin_info(r1).items()})
print("V2 引脚:", {k: v["xy"] for k, v in c.pin_info(v2).items()})

# 1) 把 R1.2 从它原来的节点里摘出来（原文件里 R1.2 和 GND 同节点）
r1p2 = next(p for p in c.ports() if p["component"] == r1 and p["name"] == "2")
for e in c.elements:
    if e.get("Class") != "CiNode":
        continue
    pe = e.find("CiNode/Ports")
    if pe is None:
        continue
    for it in list(pe):
        if it.get("CiID") == r1p2["ciid"]:
            pe.remove(it)
            print("  已把 R1.2 从节点 %s 摘出" % e.get("CiID"))
nd = r1p2["port"].find("Nodes")
if nd is not None:
    for it in list(nd):
        nd.remove(it)

# 2) V2.1 -- R1.1
n_in = a.connect([(v2, "1"), (r1, "1")], name="1")
# 3) 克隆 1pF 电容 + 地（这两个克隆，但电阻是原装）
c1, _ = a.add_part("CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=1e-12,
                   x=850.0, y=430.0, donor_path=c, donor_refdes="C1")
gnd = [x for x in c.components() if x["part"] == "GROUND"][0]["ciid"]
g1, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=850.0, y=520.0,
                   donor_path=c, donor_refdes=gnd)
n_mid = a.connect([(r1, "2"), (c1, "1")], name="2")
a.connect([(c1, "2"), (g1, "1")], name="0")
print("节点 in=%s mid=%s" % (n_in, n_mid))

# 4) 探针放中点导线拐点
cinfo = c.pin_info(c1)
rinfo = c.pin_info(r1)
px, py = cinfo["1"]["xy"][0], rinfo["2"]["xy"][1]
clone_probe_ext(a, PROBE_DONOR, px, py)
print("探针 @ (%g,%g)" % (px, py))

n, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))
back = msmodel.Circuit.load(OUT)
pm = {p["ciid"]: p for p in back.ports()}
for nd2 in back.nodes():
    names = []
    for pid in nd2["ports"]:
        p = pm.get(pid)
        if p:
            ref = next((x["refdes"] for x in back.components() if x["ciid"] == p["component"]), "?")
            names.append("%s.%s" % (ref, p["name"]))
    print("  node %-10s name=%-3r ports=%s" % (nd2["ciid"], nd2["name"], names))
for e in back.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        print("  wire Node=%s pts=%s" % (inner[0].get("Node"),
              [(p.get("X"), p.get("Y")) for p in inner[0].find("Points")]))
