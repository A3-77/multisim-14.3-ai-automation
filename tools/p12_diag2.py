# -*- coding: utf-8 -*-
"""P12 诊断2：rc_lowpass 里每个元件的 CiModel 是否落地；与 donor 原件对比。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

TARGET = os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14")

c = msmodel.Circuit.load(TARGET)
print("=== rc_lowpass ===")
for comp in c.components():
    inner = comp["comp"]
    mid = inner.get("Model")
    found = any(e.get("CiID") == mid for e in c.elements) if mid else False
    print("  %-3s %-16s %-22s Model=%-12r 落地=%s" %
          (comp["refdes"], comp["family"], comp["part"], mid, found))
    print("      slot1: %s" % (ET.tostring(list(inner.find("Attributes"))[1],
                                           encoding="unicode")[:150].replace("\n", " ")))
    print("      slot4: %s" % (ET.tostring(list(inner.find("Attributes"))[4],
                                           encoding="unicode")[:200].replace("\n", " ")))

print()
print("=== donor 原件 ===")
for fam, part, ref in (("RESISTOR", "RESISTOR_VIRTUAL", "R4"),
                       ("CAPACITOR", "CAPACITOR_VIRTUAL", "C1"),
                       ("POWER_SOURCES", "DC_POWER", "V1"),
                       ("POWER_SOURCES", "GROUND", "0")):
    hit = msbuild.find_part(fam, part)
    d = msbuild.load_donor(hit[0])
    comp = d.find(hit[1])
    inner = comp["comp"]
    mid = inner.get("Model")
    found = any(e.get("CiID") == mid for e in d.elements) if mid else False
    print("  %s#%s %-16s %-22s Model=%-12r 落地=%s" % (os.path.basename(hit[0]), hit[1],
          comp["family"], comp["part"], mid, found))
    print("      slot1: %s" % (ET.tostring(list(inner.find("Attributes"))[1],
                                           encoding="unicode")[:150].replace("\n", " ")))
