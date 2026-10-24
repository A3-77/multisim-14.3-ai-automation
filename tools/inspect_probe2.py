# -*- coding: utf-8 -*-
"""看探针的绘图对象、位置，以及 CiCircuit/ProbeExts 里怎么关联节点。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = os.path.join(ROOT, "out", "samples",
                 "LabVIEW-Multisim Co-simulation__Brushed DC Motor__DC Motor - Ideal H Bridge.ms14")

r = ET.parse(P).getroot()
d = r.find(".//CIITDiagram")

cc = d.find("Elements").find("Item[@Class='CiCircuit']")
print("=== CiCircuit ===")
print(ET.tostring(cc, encoding="unicode")[:1200])

pr = d.find(".//CiProbeComp")
sid = pr.get("SymCompID")
print("\n探针 SymCompID =", sid)

objs = d.find("Components/CODComposite/Objects")
for item in objs:
    if item.get("ID") == sid:
        print("\n=== 探针绘图对象 ===")
        print(ET.tostring(item, encoding="unicode")[:2000])
        break
else:
    print("绘图对象里没找到该 ID")
    # 列出所有可能的探针类
    for item in objs:
        inner = list(item)
        if inner and "Probe" in (inner[0].get("Class") or ""):
            print("  候选:", item.get("ID"), inner[0].get("Class"))
