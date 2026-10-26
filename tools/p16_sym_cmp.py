# -*- coding: utf-8 -*-
"""P16: 同一文件内 buck 原生 R1 vs 克隆 R9 的符号子树逐对象对比"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = os.path.join(ROOT, "out", "_p15_buckbase.xml")


def symbol_of(c, refdes):
    ciid = c.find(refdes)["ciid"]
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITSymbolComp" and inner[0].get("CiComponent") == ciid:
            return e
    return None


def profile(c, refdes):
    sym = symbol_of(c, refdes)
    if sym is None:
        return None, Counter()
    cnt = Counter()
    for el in sym.iter():
        cls = el.get("Class") or el.tag
        cnt[cls] += 1
    return sym, cnt


c = msmodel.Circuit.from_xml_file(SRC)
sa, ca = profile(c, "R1")     # buck 原生
sb, cb = profile(c, "R9")     # 克隆

print("=" * 70)
print("符号子树对象计数")
print("=" * 70)
print("%-36s %10s %10s" % ("Class", "R1(buck)", "R9(clone)"))
for k in sorted(set(ca) | set(cb)):
    mark = " <<<" if ca.get(k, 0) != cb.get(k, 0) else ""
    print("%-36s %10d %10d%s" % (k, ca.get(k, 0), cb.get(k, 0), mark))

print()
print("=" * 70)
print("符号根属性")
print("=" * 70)
ia, ib = list(sa)[0], list(sb)[0]
for k in sorted(set(ia.attrib) | set(ib.attrib)):
    va, vb = ia.get(k), ib.get(k)
    mark = " <<<" if va != vb else ""
    if mark:
        print("  %-28s buck=%-22s clone=%-22s%s" % (k, str(va)[:20], str(vb)[:20], mark))

print()
print("=" * 70)
print("引脚符号属性")
print("=" * 70)
for tag, sym in (("R1", sa), ("R9", sb)):
    print("--", tag)
    for ps in sym.iter("CIITPinSymbolComp"):
        print("   ", {k: v for k, v in ps.attrib.items()
                      if k in ("PinName", "PortID", "PinType", "PinNumber",
                               "Transformer-M20", "Transformer-M21", "InternalPin")})
