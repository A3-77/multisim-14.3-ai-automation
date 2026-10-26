# -*- coding: utf-8 -*-
"""P19-1：检查样例索引可用性（donor 模板来源是否齐全）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

idx = msbuild.part_index()
print("索引条目数:", len(idx))

want = [
    ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"),
    ("RESISTOR", "RESISTOR_VIRTUAL"),
    ("CAPACITOR", "CAPACITOR_VIRTUAL"),
    ("POWER_SOURCES", "GROUND"),
    ("POWER_SOURCES", "DC_POWER"),
]
for k in want:
    print("  %-24s %-20s -> %s" % (k[0], k[1], idx.get(k)))

print()
d = os.path.join(ROOT, "out", "samples")
print("out/samples 存在:", os.path.isdir(d))
if os.path.isdir(d):
    fs = os.listdir(d)
    print("文件数:", len(fs), " 前 3:", fs[:3])
