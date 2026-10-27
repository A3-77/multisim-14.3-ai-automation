# -*- coding: utf-8 -*-
"""探查 14.3.3 下 Multisim COM 到底暴露了哪些接口，特别是元件库相关。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

DIODE = os.path.join(ROOT, "out", "probe_parts", "diode_halfwave.ms14")

app = msc.Multisim(connect=True)   # __init__ 里已经 Connect 过了
print("版本:", app.version, "| exe:", app.exe_path, "| connected:", app.connected)

print("\n=== MultisimApp 的成员 ===")
names = sorted(n for n in dir(app._app) if not n.startswith("_"))
print("  %d 个:" % len(names))
for n in names:
    print("    " + n)

print("\n=== 打开电路后 Circuit 对象的成员 ===")
doc = app.open(DIODE)
print("  文件:", doc.file)
comps = doc.components()
print("  元件:", comps)

cir = doc._c
cnames = sorted(n for n in dir(cir) if not n.startswith("_"))
print("  %d 个:" % len(cnames))
for n in cnames:
    print("    " + n)

print("\n=== 与库/数据库相关的成员 ===")
kw = ("lib", "db", "database", "part", "component", "search", "place", "enum", "family", "group")
hits = [n for n in cnames if any(k in n.lower() for k in kw)]
print("  ", hits)

print("\n=== sections('D1') ===")
try:
    print("  ", doc.sections("D1"))
except Exception as e:
    print("   失败:", e)

print("\n=== 尝试 replace_component（用库换器件）===")
tries = [
    ("D1", "Master Database", "Diodes", "DIODE", "1N4148"),
    ("D1", "Master Database", "Diodes", "DIODE", "1N4001"),
    ("D1", "Master", "Diodes", "DIODE", "1N4148"),
]
for comp, db, grp, fam, nm in tries:
    try:
        r = doc.replace_component(comp, "", db, grp, fam, nm)
        print("  OK  %s <- %s/%s/%s/%s -> %r" % (comp, db, grp, fam, nm, r))
        break
    except Exception as e:
        print("  ERR %s <- %s/%s/%s/%s : %s" % (comp, db, grp, fam, nm, str(e)[:180]))

app.disconnect()
