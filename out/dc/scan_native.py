# -*- coding: utf-8 -*-
"""找原生样例里的 ground truth：带 DC 源 + 电阻 + 探针的电路。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dcl
import msmodel

d = os.path.join(ROOT, "corpus", "samples14")
for f in sorted(os.listdir(d)):
    if not f.lower().endswith(".ms14"):
        continue
    p = os.path.join(d, f)
    try:
        c = msmodel.Circuit.load(p)
        comps = c.components()
        raw, _ = dcl.read_ms14(p)
        xml = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        nprobe = xml.count("CiProbeExtComp")
        dc = sum(1 for x in comps if "DC_POWER" in str(x.get("part")))
        r = sum(1 for x in comps if x.get("family") == "RESISTOR")
        cap = sum(1 for x in comps if x.get("family") == "CAPACITOR")
        simstate = 'SimState=""' in xml
        print("%-34s 元件%3d  DC%2d  R%2d  C%2d  探针%2d  SimState空=%s"
              % (f, len(comps), dc, r, cap, nprobe, simstate))
    except Exception as e:
        print("%-34s ERR %s" % (f, e))
