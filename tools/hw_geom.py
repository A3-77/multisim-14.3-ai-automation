# -*- coding: utf-8 -*-
"""打印各元件的引脚几何（相对原点）与引脚质心，便于手工摆位。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import registry  # noqa: E402

WANT = [
    ("POWER_SOURCES", "DC_POWER"),
    ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"),
    ("RESISTOR", "RESISTOR_VIRTUAL"),
    ("CAPACITOR", "CAPACITOR_VIRTUAL"),
    ("CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL"),
    ("POWER_SOURCES", "GROUND"),
    ("BJT_NPN", "2N2222A"),
    ("POTENTIOMETER", "POTENTIOMETER_VIRTUAL"),
    ("OPAMP", "741"),
    ("ZENER", "1N4734A"),
]

for fam, part in WANT:
    e = registry.spec(fam, part)
    if not e:
        print("MISS", fam, part)
        continue
    g = e.get("pin_geometry") or {}
    pts = list(g.values())
    cx = sum(p[0] for p in pts) / len(pts) if pts else 0
    cy = sum(p[1] for p in pts) / len(pts) if pts else 0
    rel = {k: (round(v[0] - cx, 2), round(v[1] - cy, 2)) for k, v in g.items()}
    print("%-26s %-24s centroid=(%.1f,%.1f) orient=%s"
          % (fam, part, cx, cy, e.get("orientation")))
    print("    rel:", json.dumps(rel, ensure_ascii=False))
