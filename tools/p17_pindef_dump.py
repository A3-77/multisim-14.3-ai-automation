# -*- coding: utf-8 -*-
"""P17: 只打印「有子元素」的 CODPinComp 定义，完整 XML。

用法: runtime\py32\python.exe tools\p17_pindef_dump.py <ms14> [数量]
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2
c = msmodel.Circuit.load(SRC)


def pretty(el):
    xml = ET.tostring(el, encoding="unicode")
    try:
        import xml.dom.minidom as md
        return md.parseString(xml).toprettyxml(indent="  ")
    except Exception:
        return xml


defs = [e for e in c.tree.iter("Item")
        if e.get("Class") == "CODPinComp" and len(list(e))]
print("有子元素的 CODPinComp 定义: %d" % len(defs))
for e in defs[:N]:
    print("=" * 60)
    print(pretty(e)[:2200])
