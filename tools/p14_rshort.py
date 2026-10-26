# -*- coding: utf-8 -*-
"""P14e: R1 改成 1e-6Ω（近似短路），判别 R1 是否在 SPICE deck 里"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "out", "p13_a3.ms14")
OUT = os.path.join(ROOT, "out", "p14_rshort.ms14")

xml, _ = dcl.read_ms14(SRC)
p = os.path.join(ROOT, "out", "_p14_a3src2.xml")
open(p, "wb").write(xml)
c = msmodel.Circuit.from_xml_file(p)

for ref, val, disp in (("R1", "1e-06", "&ASC1u"),):
    comp = c.find(ref)["comp"]
    pl = list(comp.find("Attributes"))[2].find("CiaParamList")
    nums = pl.find("doubles").findall("Item")
    ps = pl.find("parameters").findall("Item")
    print("%s 原值: doubles=%s params=%s" % (ref, nums[1].get("Value"), ps[1].get("Value")))
    nums[1].set("Value", val)
    ps[1].set("Value", disp)
    print("%s 新值: doubles=%s params=%s" % (ref, nums[1].get("Value"), ps[1].get("Value")))

c.save(OUT)
print("已保存:", OUT, os.path.getsize(OUT))
