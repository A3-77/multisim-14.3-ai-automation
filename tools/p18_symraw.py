# -*- coding: utf-8 -*-
"""P18: 打印某元件符号对象的原始 XML 头部，看 CIITSymbolComp 有没有 Transformer 变换。

用法: runtime\py32\python.exe tools\p18_symraw.py <ms14> <refdes>
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

sym_of = {}
for e in c.elements:
    if e.get("Class") == "CiComponent":
        inner = list(e)[0]
        ln = (inner.get("LocalName") or "").replace("&ASC", "")
        sym_of[ln] = inner.get("SymCompID")
sid = sym_of.get(REF)
print("%s %s SymCompID=%s" % (os.path.basename(SRC), REF, sid))

for e in c.objects:
    if e.get("ID") != sid:
        continue
    print("Item 直接子元素:", [ch.tag for ch in e])
    inner = list(e)[0]
    print("第一个子元素 tag=%s attrib=%s" % (inner.tag, inner.attrib))
    # 打印所有 CIITSymbolComp 元素的属性
    for el in e.iter("CIITSymbolComp"):
        print("  CIITSymbolComp attrib:")
        for k, v in el.attrib.items():
            print("      %s=%r" % (k, v))
    break
