# -*- coding: utf-8 -*-
"""P16b: 给克隆元件的引脚符号补 PinType=&ASCGRP:A，看电阻是否导通"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "out", "p15_divider.ms14")
OUT = os.path.join(ROOT, "out", "p16_pintype.ms14")

xml, _ = dcl.read_ms14(SRC)
p = os.path.join(ROOT, "out", "_p16_src.xml")
open(p, "wb").write(xml)
c = msmodel.Circuit.from_xml_file(p)

n = 0
for ps in c.tree.iter("CIITPinSymbolComp"):
    old = ps.get("PinType")
    ps.set("PinType", "&ASCGRP:A")
    n += 1
    print("  %-8s %-8s PinType %r -> &ASCGRP:A" % (ps.get("PinName"), ps.get("PortID"), old))
print("共改 %d 个" % n)

c.save(OUT)
print("写出", OUT, os.path.getsize(OUT))
