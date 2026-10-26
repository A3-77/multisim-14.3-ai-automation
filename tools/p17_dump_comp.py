# -*- coding: utf-8 -*-
"""P17: 导出指定 refdes 的 CiComponent 完整 XML（按 LocalName=&ASC<refdes> 匹配）。

用法: runtime\py32\python.exe tools\p17_dump_comp.py <ms14> <refdes>
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC, REF = sys.argv[1], sys.argv[2]
c = msmodel.Circuit.load(SRC)

want = "&ASC" + REF
found = []
for e in c.elements:
    if e.get("Class") != "CiComponent":
        continue
    inner = list(e)[0]
    if inner.get("LocalName") == want:
        found.append(e)

if not found:
    raise SystemExit("没找到 LocalName=%s" % want)
print("命中 %d 个" % len(found))
for e in found[:1]:
    inner = list(e)[0]
    print("CiID=%s SymCompID=%s InstanceID=%s" % (
        e.get("CiID"), inner.get("SymCompID"), inner.get("InstanceID")))
    xml = ET.tostring(inner, encoding="unicode")
    # 换行美化
    try:
        import xml.dom.minidom as md
        xml = md.parseString(xml).toprettyxml(indent="  ")
    except Exception:
        pass
    print(xml)
