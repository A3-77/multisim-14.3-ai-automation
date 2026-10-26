# -*- coding: utf-8 -*-
"""P17: 打印探针 donor 里 ProbeExt 的完整结构，找名字存在哪个属性。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

p = os.path.join(ROOT, "out", "ref", "with_probes.ms14")
c = msmodel.Circuit.load(p)
print("summary:", c.summary())

for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITProbeExtComponent":
        print("=== DRAW", e.get("ID"))
        print(ET.tostring(inner[0], encoding="unicode")[:4000])

for e in c.elements:
    if e.get("Class") in ("CiProbeExtComp", "CiProbeComp"):
        print("=== ELEC", e.get("Class"), e.get("CiID"))
        print(ET.tostring(list(e)[0], encoding="unicode")[:2000])
