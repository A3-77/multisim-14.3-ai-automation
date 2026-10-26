# -*- coding: utf-8 -*-
"""P18: 对比导线的完整 XML —— 重点看 ElectricalObject/ModifierInfo 里的网络名。

ReportNetlist 走 CiNode/Ports（所以永远正确）；SPICE 网表走绘图侧的
CIITLinkComp，网络归属可能存在 ElectricalObject/ModifierInfo 里。
若这里是空的，导线就不属于任何网络。

用法: runtime\py32\python.exe tools\p18_wirefull.py <ms14> [条数]
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


wires = [e for e in c.tree.iter("Item") if e.get("Class") == "CIITLinkComp"]
print("%s: 导线 %d" % (os.path.basename(SRC), len(wires)))
for e in wires[:N]:
    print("=" * 60)
    print(pretty(e)[:2600])
