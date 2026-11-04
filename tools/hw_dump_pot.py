# -*- coding: utf-8 -*-
"""看电位器元件里到底把"百分比"存在哪。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

p = os.path.join(ROOT, "out", "hw1", "ce_amp_p10.ms14")
c = msbuild.load_donor(p)
for d in c.components():
    if d["refdes"] != "RW":
        continue
    for el in c.elements:
        if el.get("CiID") == d["ciid"]:
            s = ET.tostring(el, encoding="unicode")
            print(s[:6000])
