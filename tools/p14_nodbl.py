# -*- coding: utf-8 -*-
"""P14s: 清空 R1/R2 的 doubles 数组（对齐 buck 原生格式），看是否让电阻进 deck"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "out", "p14_div_r.ms14")
OUT = os.path.join(ROOT, "out", "p14_div_nodbl.ms14")

xml, _ = dcl.read_ms14(SRC)
p = os.path.join(ROOT, "out", "_p14_div_nodbl.xml")
open(p, "wb").write(xml)
c = msmodel.Circuit.from_xml_file(p)

for ref in ("R1", "R2"):
    comp = c.find(ref)["comp"]
    pl = list(comp.find("Attributes"))[2].find("CiaParamList")
    doubles = pl.find("doubles")
    nums = doubles.findall("Item")
    print("%s doubles: %s" % (ref, [n.get("Value") for n in nums]))
    for n in nums:
        doubles.remove(n)
    ps = pl.find("parameters")
    print("   params: %s" % [x.get("Value") for x in ps.findall("Item")])
    ind = pl.find("paramindicators")
    print("   indicators: %s" % [x.get("Value") for x in ind.findall("Item")] if ind is not None else None)

c.save(OUT)
print("写出", OUT, os.path.getsize(OUT))
