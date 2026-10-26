# -*- coding: utf-8 -*-
"""扫描 corpus/samples14 下每个 .ms14 的元件构成，挑合适的供体。

关注：GND 数量（>=2 才能搭两个独立接地点）、有无 RESISTOR_VIRTUAL /
CAPACITOR_VIRTUAL / DC_POWER、有无探针。

用法: runtime\py32\python.exe tools\p18_scan.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

D = os.path.join(ROOT, "corpus", "samples14")
for fn in sorted(os.listdir(D)):
    if not fn.lower().endswith(".ms14"):
        continue
    p = os.path.join(D, fn)
    try:
        c = msmodel.Circuit.load(p)
    except Exception as e:
        print("%-42s 读取失败 %s" % (fn, e))
        continue
    comps = c.components()
    gnd = sum(1 for x in comps if x["part"] == "GROUND")
    rv = [x["refdes"] for x in comps if x["part"] == "RESISTOR_VIRTUAL"]
    cv = [x["refdes"] for x in comps if x["part"] in
          ("CAPACITOR_VIRTUAL", "CAP_ELECTROLIT_VIRTUAL")]
    dc = [x["refdes"] for x in comps if x["part"] in ("DC_POWER", "DC_POWER_VIRTUAL")]
    pr = 0
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") in ("CIITProbeExtComponent", "CIITProbeComponent"):
            pr += 1
    print("%-42s 元件=%-3d GND=%d 虚拟R=%-12s 虚拟C=%-12s DC=%-6s 探针=%d"
          % (fn[:42], len(comps), gnd, ",".join(rv[:3]) or "-",
             ",".join(cv[:3]) or "-", ",".join(dc[:2]) or "-", pr))
