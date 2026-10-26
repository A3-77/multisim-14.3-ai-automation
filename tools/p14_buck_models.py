# -*- coding: utf-8 -*-
"""P14j: 原生 buck.ms14 里电阻/电容是否有 CiModel，模型长什么样"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = r"C:\Users\A377\Downloads\multisim_simulations\aareyes96-multisim_simulations-daff854\buck.ms14"

xml, _ = dcl.read_ms14(SRC)
p = os.path.join(ROOT, "out", "_p14_buck.xml")
open(p, "wb").write(xml)
c = msmodel.Circuit.from_xml_file(p)

print("=== 元件清单 ===")
for comp in c.components():
    item = c._item_of(comp["ciid"])
    inner = item.find("CiComponent")
    mid = inner.get("Model")
    print("  %-6s %-26s Model=%s" % (comp["refdes"], comp["part"], mid))

print()
print("=== CiModel 列表 ===")
for e in c.elements:
    if e.get("Class") != "CiModel":
        continue
    inner = e.find("CiModel")
    print("--- CiID=%s ---" % e.get("CiID"))
    print("   属性:", {k: v for k, v in inner.attrib.items()})
    s = ET.tostring(e, encoding="unicode")
    print("   XML 长度 %d" % len(s))
    print("   ", s[:1200].replace("\n", " "))
    print()
