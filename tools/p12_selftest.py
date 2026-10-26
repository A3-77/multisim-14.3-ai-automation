# -*- coding: utf-8 -*-
"""P12 自检：add_part 能否按 (family, part) 找到样例并克隆，异常提示是否清晰。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild

idx = msbuild.part_index()
print("索引组合数:", len(idx))
print("RESISTOR 家族:", [k for k in idx if k[0] == "RESISTOR"][:6])
print("CAPACITOR 家族:", [k for k in idx if k[0] == "CAPACITOR"][:6])

for fam, part in (("RESISTOR", "RESISTOR_VIRTUAL"), ("CAPACITOR", "CAPACITOR_VIRTUAL"),
                  ("POWER_SOURCES", "DC_POWER"), ("POWER_SOURCES", "GROUND"),
                  ("INDUCTOR", "INDUCTOR_VIRTUAL"), ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE")):
    hit = msbuild.find_part(fam, part)
    print("  find_part(%-24s,%-20s) -> %s" % (fam, part,
          os.path.basename(hit[0]) + "#" + hit[1] if hit else None))

a = msbuild.Assembler()
ciid, ports = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R9", value=4700.0, x=100.0, y=100.0)
print("add_part 成功: ciid=%s ports=%s" % (ciid, ports))
print("  参数:", a.c.params(a.c.find("R9")["comp"])[:2])
print("  来源:", a.last_part["donor_refdes"], a.last_part["donor_family"],
      a.last_part["donor_part"], "->", os.path.basename(a.last_part["donor"]))

print()
print("异常提示测试:")
try:
    a.add_part("RESISTORR", "RESISTOR_VIRTUAL", "R8")
except KeyError as e:
    print("  KeyError OK:")
    print("  " + str(e).replace("\n", "\n  ")[:400])

try:
    a.add_part("CAPACITOR", "CAPACITOR_VIRTUAL", "C8", donor_path="x")
except ValueError as e:
    print("  ValueError OK:", e)
