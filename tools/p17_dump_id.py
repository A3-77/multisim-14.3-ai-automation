# -*- coding: utf-8 -*-
"""P17: 按 CiID 导出任意元素（在 Elements / Objects / ReferencedComponents 三棵树里找）。

用法: runtime\py32\python.exe tools\p17_dump_id.py <ms14> <CiID> [<CiID> ...]
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
IDS = sys.argv[2:]
c = msmodel.Circuit.load(SRC)


def pretty(el):
    xml = ET.tostring(el, encoding="unicode")
    try:
        import xml.dom.minidom as md
        return md.parseString(xml).toprettyxml(indent="  ")
    except Exception:
        return xml


for cid in IDS:
    hit = 0
    for e in c.tree.iter("Item"):
        if e.get("CiID") == cid or e.get("ID") == cid:
            hit += 1
            print("### CiID/ID=%s Class=%s" % (cid, e.get("Class")))
            print(pretty(e))
            if hit >= 3:
                break
    if not hit:
        print("### CiID/ID=%s 未找到" % cid)
