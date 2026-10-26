# -*- coding: utf-8 -*-
"""探布局：打印候选位置的引脚坐标。"""
import os
import sys
import gzip

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

donor = msmodel.Circuit(gzip.open(os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz"),
    "rb").read())

a = msbuild.Assembler()
dv = msbuild.Donor(donor, "V2")
v1, vp = a.add(dv, x=360.0, y=300.0, refdes="V1")
dr = msbuild.Donor(donor, "R1")
r1, rp = a.add(dr, x=520.0, y=300.0, refdes="R1")
dc = msbuild.Donor(donor, "C1")
c1, cp = a.add(dc, x=300.0, y=430.0, refdes="C1")
gnd_ref = [c for c in donor.components() if c["part"] == "GROUND"][0]["refdes"]
g1, _ = a.add(msbuild.Donor(donor, gnd_ref), x=520.0, y=430.0)
g2, _ = a.add(msbuild.Donor(donor, gnd_ref), x=360.0, y=430.0)

for tag, cid in (("V1", v1), ("R1", r1), ("C1", c1), ("GND1", g1), ("GND2", g2)):
    info = a.c.pin_info(cid)
    print("%-5s %s" % (tag, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                             for k, v in info.items()}))
