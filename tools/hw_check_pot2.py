# -*- coding: utf-8 -*-
"""统计 ms14 里的探针对象与导线数量。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

p = os.path.join(ROOT, "out", "hw1", "pot_i3_10.ms14")
s = open(p, encoding="utf-8", errors="ignore").read()
print("len", len(s))
for k in ("ProbeExt", "CIITLinkComp", 'Class="CiComponent"', "CiProbeComp",
          "NetName", "Probe"):
    print("%-22s %d" % (k, s.count(k)))
i = s.find("ProbeExt")
print(s[max(0, i - 200):i + 600])
