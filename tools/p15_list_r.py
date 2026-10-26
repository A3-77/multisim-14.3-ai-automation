# -*- coding: utf-8 -*-
"""列出某个 (family, part) 的所有可用模板来源，方便挑一个干净的 donor。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild

fam = sys.argv[1] if len(sys.argv) > 1 else "RESISTOR"
part = sys.argv[2] if len(sys.argv) > 2 else "RESISTOR_VIRTUAL"

idx = msbuild.part_index()
lst = idx.get((fam, part), [])
print("(%s, %s) 候选 %d 个：" % (fam, part, len(lst)))
for p, ref in lst:
    print("  %-6s %s" % (ref, os.path.basename(p)))

print()
print("语料里所有含 RESISTOR 的家族：")
for (f, p), v in sorted(idx.items()):
    if "RESIST" in (f or "").upper():
        print("  %-28s %-30s %d 个" % (f, p, len(v)))
