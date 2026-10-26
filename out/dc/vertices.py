# -*- coding: utf-8 -*-
"""看 net_vertices 到底给了哪些点（探针必须落在导线顶点上）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import msbuild

a = msbuild.Assembler()
v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=5.0, x=300, y=300)
r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0, x=500, y=300)
gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=300, y=420)

print("V1 引脚", a.c.pin_info(v1))
print("R1 引脚", a.c.pin_info(r1))
print("GND 引脚", a.c.pin_info(gnd))

n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
n_g = a.connect([(v1, "2"), (gnd, "1"), (r1, "2")], name="0")
print("\nnet in  =", n_in, "顶点:", a.net_vertices(n_in))
print("net 0   =", n_g, "顶点:", a.net_vertices(n_g))
