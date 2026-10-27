# -*- coding: utf-8 -*-
"""试 ReplaceComponent 的 source_database 枚举值，看 COM 能否直接按库换器件。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

DIODE = os.path.join(ROOT, "out", "probe_parts", "diode_halfwave.ms14")

app = msc.Multisim(connect=True)
d = app.open(DIODE)
print("元件:", d.components(), " sections(D1):", d.sections("D1"))

CANDIDATES = [
    (0, "Diodes", "DIODE", "1N4148"),
    (0, "Diodes", "DIODE", "1N4001"),
    (0, "Diode", "DIODE", "1N4148"),
    (1, "Diodes", "DIODE", "1N4148"),
    (2, "Diodes", "DIODE", "1N4148"),
    (0, "Master", "DIODE", "1N4148"),
]
for db, grp, fam, nm in CANDIDATES:
    try:
        r = d.replace_component("D1", "", db, grp, fam, nm)
        print("  OK   db=%s %s/%s/%s -> %r" % (db, grp, fam, nm, r))
        print("       换后元件:", d.components())
        break
    except Exception as e:
        msg = str(e).split("'")[-2] if "'" in str(e) else str(e)
        print("  ERR  db=%s %-8s %-8s %-8s : %s" % (db, grp, fam, nm, str(e)[:130]))

print("\n--- 反向确认：用不存在的型号，看错误是否更具体 ---")
try:
    d.replace_component("D1", "", 0, "Diodes", "DIODE", "NOSUCHPART")
except Exception as e:
    print("  ", str(e)[:220])

app.disconnect()
