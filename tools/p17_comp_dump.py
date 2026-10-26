# -*- coding: utf-8 -*-
"""P17: 把某个 refdes 的 CiComponent 完整 XML（含 Attributes/CiModel 引用）导出，
用于 donor 原生 vs 克隆件 的逐字对比。

用法: runtime\py32\python.exe tools\p17_comp_dump.py <ms14> <refdes> [--model]
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
REF = sys.argv[2]
WANT_MODEL = "--model" in sys.argv

c = msmodel.Circuit.load(SRC)

# 1) 元件本体
target = None
for e in c.elements:
    if e.get("Class") == "CiComponent":
        inner = list(e)[0]
        if inner.get("LocalName") == REF or inner.get("RefDes") == REF:
            target = e
            break
if target is None:
    # 退一步：按 InstanceRefDes 属性找
    for e in c.elements:
        if e.get("Class") == "CiComponent":
            for it in list(e)[0].iter("Item"):
                if it.get("Value") == REF:
                    target = e
                    break
        if target is not None:
            break
if target is None:
    raise SystemExit("找不到 refdes=%s" % REF)

inner = list(target)[0]
print("=== CiComponent %s  attrkeys=%s" % (target.get("CiID"), list(inner.attrib.keys())))
print(ET.tostring(inner, encoding="unicode"))

# 2) 引用的 CiModel
if WANT_MODEL:
    ids = set()
    for el in inner.iter():
        for k, v in el.attrib.items():
            if v and v.isdigit() and len(v) >= 6:
                ids.add(v)
    for e in c.elements:
        cid = e.get("CiID") or e.get("ID")
        if cid in ids:
            print("=== 关联元素 %s Class=%s" % (cid, e.get("Class")))
            print(ET.tostring(list(e)[0], encoding="unicode")[:3000])
