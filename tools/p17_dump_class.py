# -*- coding: utf-8 -*-
"""P17: 按 Class 名导出若干实例（完整 XML），用于研究缺失结构。

用法: runtime\py32\python.exe tools\p17_dump_class.py <ms14> <Class> [数量]
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
CLS = sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 2
c = msmodel.Circuit.load(SRC)


def pretty(el):
    xml = ET.tostring(el, encoding="unicode")
    try:
        import xml.dom.minidom as md
        return md.parseString(xml).toprettyxml(indent="  ")
    except Exception:
        return xml


hits = [e for e in c.tree.iter() if e.get("Class") == CLS]
print("命中 %d 个 %s（含非 Item 元素）" % (len(hits), CLS))
for e in hits[:N]:
    print("-" * 60)
    print("tag=%s ID=%s CiID=%s" % (e.tag, e.get("ID"), e.get("CiID")))
    print(pretty(e)[:2500])
