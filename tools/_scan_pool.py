# -*- coding: utf-8 -*-
"""扫描当前 donor 池：corpus + Multisim 官方样例，列出所有可用 (family, part)。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
import msbuild

print("DONOR_DIRS      :", msbuild.DONOR_DIRS)
print("INSTALL_SAMPLES :", msbuild.INSTALL_SAMPLES,
      "| 存在:", os.path.isdir(msbuild.INSTALL_SAMPLES))

if os.path.isdir(msbuild.INSTALL_SAMPLES):
    n = 0
    for root, dirs, files in os.walk(msbuild.INSTALL_SAMPLES):
        n += len([x for x in files if x.lower().endswith(".ms14")])
    print("  官方样例 .ms14 数量:", n)
    print("  子目录:", sorted(os.listdir(msbuild.INSTALL_SAMPLES))[:25])

idx = msbuild.part_index()
print("\n=== corpus 索引：%d 个 (family, part) ===" % len(idx))
for (fam, part), lst in sorted(idx.items()):
    print("  %-30s %-28s x%d  <- %s" % (fam, part, len(lst), os.path.basename(lst[0][0])))

print("\n=== 目标元件是否有 donor ===")
targets = [
    ("DIODE", None), ("DIODE", "DIODE"), ("DIODE", "DIODE_VIRTUAL"), ("DIODE", "LED"),
    ("TRANSISTOR", None), ("TRANSISTOR", "NPN"), ("TRANSISTOR", "NPN_VIRTUAL"),
    ("TRANSISTOR", "BJT_NPN"), ("TRANSISTOR", "2N2222A"),
    ("ANALOG", None), ("ANALOG", "OPAMP"), ("ANALOG", "THREE_TERMINAL_VIRTUAL"),
    ("TRANSISTOR", "MOSFET"), ("TRANSISTOR", "NMOS"), ("TRANSISTOR", "MOSFET_N"),
]
for fam, part in targets:
    hit = msbuild.find_part(fam, part)
    print("  %-14s %-22s -> %s" % (fam, part, ("OK  " + os.path.basename(hit[0]) + " [" + hit[1] + "]") if hit else "MISS"))
