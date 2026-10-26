# -*- coding: utf-8 -*-
"""新 acceptance（100uF，GND 已修）vs p10：剩余差异深挖。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import xml.etree.ElementTree as ET

mine = msmodel.Circuit.from_xml_file("out/_accept.xml")
p10 = msmodel.Circuit.from_xml_file("out/_p10.xml")

for label, c in (("mine", mine), ("p10", p10)):
    print("=== %s ===" % label)
    # 导线完整属性
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp":
            lnk = inner[0]
            pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
            print("  wire %s M20/M21=%s/%s Node=%s pts=%s"
                  % (e.get("ID"), lnk.get("Transformer-M20"), lnk.get("Transformer-M21"),
                     lnk.get("Node"), pts))
    # 探针
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeExtComponent":
            di = inner[0]
            print("  probe M20/M21=%s/%s" % (di.get("Transformer-M20"), di.get("Transformer-M21")))
    # 节点名与成员
    print("  节点:")
    ref2ciid = {}
    for comp in c.components():
        ref2ciid.setdefault(comp["refdes"], []).append(comp["ciid"])
    ciid2ref = {v: k for k, vs in ref2ciid.items() for v in vs}
    for e in c.elements:
        if e.get("Class") == "CiNode":
            inner = list(e)[0]
            ports = [i.get("CiID") for i in inner.find("Ports").findall("Item")]
            names = []
            for pid in ports:
                for p in c.ports():
                    if p["ciid"] == pid:
                        names.append("%s.%s" % (ciid2ref.get(p["component"], "?"), p["name"]))
            print("    %-12s name=%-8s ports=%s" % (e.get("CiID"), inner.get("LocalName"), names))
    print()
