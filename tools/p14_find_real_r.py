# -*- coding: utf-8 -*-
"""P14：在样例库里找「非虚拟」电阻/电容（part 不含 VIRTUAL），并确认原始样例文件可读。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild

idx = msbuild.part_index()
print("=== 所有含 R/C 的家族-型号 ===")
for (fam, part) in sorted(idx):
    f = (fam or "").upper()
    p = (part or "").upper()
    if "RESIST" in f or "RESIST" in p or "CAPACIT" in f or "CAPACIT" in p:
        virt = "VIRTUAL" in p
        print("  %-14s %-24s %s x%d" % (fam, part, "虚拟" if virt else "实体*", len(idx[(fam, part)])))

print()
print("=== 原始样例文件是否可读（corpus/samples_index.json 的 file 字段）===")
data = json.load(open(os.path.join(ROOT, "corpus", "samples_index.json"), encoding="utf-8"))
ok = [e for e in data if os.path.exists(e.get("file") or "")]
print("  可访问 %d / %d" % (len(ok), len(data)))
for e in ok[:3]:
    print("   ", e["file"])

print()
print("=== 在这些原始文件里找实体电阻 ===")
import msmodel
found = 0
for e in ok:
    try:
        c = msmodel.Circuit.load(e["file"])
    except Exception:
        continue
    for comp in c.components():
        p = (comp["part"] or "").upper()
        if ("RESIST" in p or "RESIST" in (comp["family"] or "").upper()) and "VIRTUAL" not in p:
            print("  %-40s %-5s %-14s %s"
                  % (e["rel"][:40], comp["refdes"], comp["family"], comp["part"]))
            found += 1
            if found >= 12:
                break
    if found >= 12:
        break
print("  找到实体电阻 %d 个（上限 12）" % found)
