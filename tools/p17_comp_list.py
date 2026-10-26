# -*- coding: utf-8 -*-
"""P17: 列出文件里所有元件的 CiID / LocalName / RefDes 属性，确定怎么按 refdes 定位。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

c = msmodel.Circuit.load(sys.argv[1])
print("summary:", c.summary())
for e in c.elements:
    if e.get("Class") != "CiComponent":
        continue
    inner = list(e)[0]
    attrs = inner.attrib
    print("CiID=%s keys=%s" % (e.get("CiID"), list(attrs.keys())))
    for k in ("LocalName", "InstanceRefDes", "Name", "RefDes", "PartName", "SectionName"):
        if k in attrs:
            print("    %s=%r" % (k, attrs[k]))
    # Attributes 里的 CiaCollString 通常是 RefDes 等
    for i, item in enumerate(inner.findall("Attributes/Item")):
        txt = ET.tostring(item, encoding="unicode")
        if "CiaCollString" in txt:
            vals = [s.get("Value") for s in item.iter("Item")]
            print("    Attr[%d] CiaCollString=%s" % (i, vals))
