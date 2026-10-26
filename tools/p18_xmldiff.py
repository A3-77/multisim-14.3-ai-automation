# -*- coding: utf-8 -*-
"""P18: 找出 ET 重新序列化到底改了什么 —— 排除无害差异后定位真正的问题。

已知无害：XML 声明引号/大小写、自闭合标签多一个空格。
其余差异就是真凶。

用法: runtime\py32\python.exe tools\p18_xmldiff.py
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl

SRC = os.path.join(ROOT, "corpus", "samples14",
                   "Amplificador para resistencia de 1mOhm.ms14")
xml, info = dcl.read_ms14(SRC)
xml2 = ET.tostring(ET.fromstring(xml), encoding="ascii", xml_declaration=True)

def norm(b):
    s = b.decode("ascii", "replace")
    s = s.replace("<?xml version='1.0' encoding='ascii'?>", "")
    s = s.replace('<?xml version="1.0" encoding="ASCII"?>', "")
    s = re.sub(r"\s*/>", "/>", s)      # <Item /> -> <Item/>
    return s

a, b = norm(xml), norm(xml2)
print("归一化后长度: 原 %d  新 %d  差 %+d" % (len(a), len(b), len(b) - len(a)))

if a == b:
    print("归一化后完全相同 —— 差异只在声明/自闭合空格，但仿真仍坏，说明另有原因")
else:
    # 逐行比较
    la, lb = a.split("\n"), b.split("\n")
    print("行数: 原 %d 新 %d" % (len(la), len(lb)))
    shown = 0
    for i in range(min(len(la), len(lb))):
        if la[i] != lb[i]:
            print("-" * 60)
            print("第 %d 行" % (i + 1))
            print("  原: %r" % la[i][:300])
            print("  新: %r" % lb[i][:300])
            shown += 1
            if shown >= 8:
                break
    if shown == 0:
        print("前面行都一样，差异在尾部长度")

# 统计实体/转义差异
for name, s in (("原", a), ("新", b)):
    print("%s: '&' 数=%d  '&amp;' 数=%d  '&#' 数=%d  制表符=%d"
          % (name, s.count("&"), s.count("&amp;"), s.count("&#"), s.count("\t")))
