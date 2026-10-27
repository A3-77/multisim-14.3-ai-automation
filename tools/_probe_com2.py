# -*- coding: utf-8 -*-
"""COM 连接方式排查：Dispatch 后直接 open 能不能行。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

DIODE = os.path.join(ROOT, "out", "probe_parts", "diode_halfwave.ms14")

print("--- 方式 1: Multisim(connect=True) ---")
try:
    a = msc.Multisim(connect=True)
    print("   OK connected=", a.connected)
    a.disconnect()
except Exception as e:
    print("   ERR", str(e)[:160])

time.sleep(2)
print("\n--- 方式 2: Multisim(connect=False) 直接 open ---")
try:
    a = msc.Multisim(connect=False)
    print("   Dispatch 成功, connected=", a.connected)
    d = a.open(DIODE)
    print("   open OK, file=", d.file, " components=", d.components())
    print("   sections('D1')=", d.sections("D1"))
    print("\n   === Circuit 成员 ===")
    names = sorted(n for n in dir(d._c) if not n.startswith("_"))
    print("   共 %d 个" % len(names))
    for n in names:
        print("     " + n)
    print("\n   === App 成员 ===")
    anames = sorted(n for n in dir(a._app) if not n.startswith("_"))
    print("   共 %d 个: %s" % (len(anames), anames))
    a.disconnect()
except Exception as e:
    print("   ERR", str(e)[:300])
