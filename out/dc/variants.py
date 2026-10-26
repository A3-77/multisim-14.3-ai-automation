# -*- coding: utf-8 -*-
"""构造对照电路：把"有没有动态元件"和"源是 DC 还是 AC"两个变量拆开。

    v1  DC + R          ← 目标电路（当前失败）
    v2  AC + R          ← 只有源不同
    v3  DC + R + C      ← 只有电容不同（v0.2.0 实测 5.0V 的那个拓扑）
    v4  AC + R + C      ← 全都有（v0.3.0 的 RC 低通，已知能读）

四个都用同一套 add_part / connect / add_probe_ext，坐标一致。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import msbuild

OUT = os.path.join(ROOT, "out", "dc")


def build(path, ac, cap):
    a = msbuild.Assembler()
    if ac:
        v1, _ = a.add_part("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                           value=1.0, x=300, y=300, params={5: 1000.0})
    else:
        v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=5.0, x=300, y=300)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0, x=500, y=300)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=300, y=420)

    if cap:
        c1, _ = a.add_part("CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=159e-9,
                           x=700, y=400)
        n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
        n_out = a.connect([(r1, "2"), (c1, "1")], name="out")
        n_g = a.connect([(v1, "2"), (gnd, "1"), (c1, "2")], name="0")
        for nid in (n_in, n_out):
            vs = a.net_vertices(nid)
            xy = vs[1] if len(vs) >= 3 else vs[0]
            a.add_probe_ext(xy[0], xy[1])
    else:
        n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
        n_g = a.connect([(v1, "2"), (gnd, "1"), (r1, "2")], name="0")
        for nid in (n_in, n_g):
            vs = a.net_vertices(nid)
            xy = vs[1] if len(vs) >= 3 else vs[0]
            a.add_probe_ext(xy[0], xy[1])
    n, _ = a.save(path)
    print("  %-28s %d 字节" % (os.path.basename(path), n))


print("构造对照电路：")
build(os.path.join(OUT, "v1_dc_r.ms14"), ac=False, cap=False)
build(os.path.join(OUT, "v2_ac_r.ms14"), ac=True, cap=False)
build(os.path.join(OUT, "v3_dc_r_c.ms14"), ac=False, cap=True)
build(os.path.join(OUT, "v4_ac_r_c.ms14"), ac=True, cap=True)
