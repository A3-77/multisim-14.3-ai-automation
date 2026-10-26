# -*- coding: utf-8 -*-
"""P19-4：诊断 add_part 的定位问题。

对每个要用的 (family, part)：
  - donor 路径与位号
  - circuit.position() 返回值（None 说明拿不到锚点）
  - 符号对象上有没有 Transformer-M20/M21
  - 引脚绝对坐标（用来反推参考点）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

WANT = [
    ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"),
    ("RESISTOR", "RESISTOR_VIRTUAL"),
    ("CAPACITOR", "CAPACITOR_VIRTUAL"),
    ("POWER_SOURCES", "GROUND"),
]

for fam, part in WANT:
    hit = msbuild.find_part(fam, part)
    print("=" * 70)
    print("%s / %s  ->  %s" % (fam, part, hit))
    if hit is None:
        continue
    path, ref = hit
    c = msbuild.load_donor(path)
    d = msbuild.Donor(c, ref)
    print("  pos          =", d.pos)
    print("  ports        =", len(d.port_items))
    sym = d.sym_item
    if sym is None:
        print("  sym_item     = None")
        continue
    inner = list(sym)[0]
    print("  sym class    =", inner.get("Class"))
    print("  sym M20/M21  = %s / %s"
          % (inner.get("Transformer-M20"), inner.get("Transformer-M21")))
    print("  sym M00..M11 = %s %s %s %s"
          % (inner.get("Transformer-M00"), inner.get("Transformer-M01"),
             inner.get("Transformer-M10"), inner.get("Transformer-M11")))
    info = c.pin_info(d.ciid)
    for k, v in info.items():
        print("   pin %-3s xy=%s" % (k, v["xy"]))
    # 符号里所有带 Transformer-M20 的子对象
    n = 0
    for el in sym.iter():
        if el.get("Transformer-M20") is not None:
            n += 1
    print("  带 Transformer-M20 的子对象数 =", n)
