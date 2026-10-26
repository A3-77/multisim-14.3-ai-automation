# -*- coding: utf-8 -*-
"""P15 判定实验：电容不跨中点，改接在电源两端（纯去耦）。

电路：V1(5V) -- R1(1k) -- MID -- R2(1k) -- GND
      C1(100nF) 跨在 V1.1 与 GND 之间（只提供动态元件让仿真能跑，不影响 MID 直流）
      探针在 MID

判定：
  MID = 2.5V  -> 电阻导通，之前所有 0V 都是「电容把中点钉到地」造成的
  MID = 0V    -> 电阻确实不导通（与电容无关）

用法：python tools/p15_div3.py
产物：out/p15_div3r.ms14
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

SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")
OUT = os.path.join(ROOT, "out", "p15_div3r.ms14")


def place(a, refdes, target, pin="1", donor=None, donor_ref=None, value=None):
    ciid, _ = a.add_part("X", "Y", refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor, donor_refdes=donor_ref)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    return ciid, a.c.pin_info(ciid)


def attach(a, ciid, pin, node_id):
    p = next(x for x in a.c.ports() if x["component"] == ciid and x["name"] == pin)
    nd = p["port"].find("Nodes")
    if nd is None:
        nd = ET.SubElement(p["port"], "Nodes")
    ET.SubElement(nd, "Item").set("CiID", node_id)
    for e in a.c.elements:
        if e.get("CiID") == node_id:
            ET.SubElement(e.find("CiNode/Ports"), "Item").set("CiID", p["ciid"])
            return
    raise KeyError(node_id)


def main():
    a = msbuild.Assembler()
    d = msbuild.load_donor(SPICE)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[3]["ciid"], "GNDC")

    # V1 在 (300,300)，R1 在 (500,340)，R2 在 (650,430)，C1 在 (450,470) 跨电源
    v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref="V2", value=5.0)
    r1, rinfo = place(a, "R1", (500.0, 340.0), donor=d, donor_ref="R1", value=1000.0)
    r2, r2info = place(a, "R2", (650.0, 430.0), donor=d, donor_ref="R1", value=1000.0)
    c1, cinfo = place(a, "C1", (450.0, 470.0), donor=d, donor_ref="C1", value=1e-7)

    # 源网：V1.1 + R1.1
    n_src = a.connect([(v1, "1"), (r1, "1")], name="1")
    # 中点：R1.2 + R2.1
    n_mid = a.connect([(r1, "2"), (r2, "1")], name="2")
    a.wire(n_mid, (r1, "2"), (r2, "1"))

    # 电容跨在源与地之间（不进中点）
    attach(a, c1, "1", n_src)
    a.wire(n_src, (r1, "1"), (c1, "1"))
    g1, _ = place(a, "0", (450.0, 560.0), donor=d, donor_ref="GNDC")
    n_gnd = a.connect([(r2, "2"), (c1, "2"), (g1, "1")], name="0")
    ga, _ = place(a, "0", (300.0, 430.0), donor=d, donor_ref="GNDA")
    a.connect([(v1, "2"), (ga, "1")], name="0")

    probe_xy = (650.0, rinfo["2"]["xy"][1])
    clone_probe_ext(a, PROBE_DONOR, *probe_xy)
    print("探针 @ (%g,%g)  中点=%s  源网=%s  地=%s"
          % (probe_xy[0], probe_xy[1], n_mid, n_src, n_gnd))

    n, _ = a.save(OUT)
    print("写出 %s (%d 字节)" % (OUT, n))
    back = msmodel.Circuit.load(OUT)
    pm = {p["ciid"]: p for p in back.ports()}
    for nd in back.nodes():
        names = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                ref = next((x["refdes"] for x in back.components()
                            if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        print("  node %-10s name=%-3r %s" % (nd["ciid"], nd["name"], names))
    for e in back.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp":
            print("  wire Node=%s pts=%s" % (inner[0].get("Node"),
                  [(p.get("X"), p.get("Y")) for p in inner[0].find("Points")]))


if __name__ == "__main__":
    main()
