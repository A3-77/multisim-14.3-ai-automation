# -*- coding: utf-8 -*-
"""强制触发 find_part 的"官方样例扩展扫描"，看全量 donor 池有多大。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
import msbuild

base = msbuild.part_index()
print("corpus 索引: %d" % len(base))

ext = msbuild._scan_dirs([msbuild.INSTALL_SAMPLES])
print("官方样例索引: %d" % len(ext))

merged = dict(base)
added = {k: v for k, v in ext.items() if k not in merged}
merged.update(added)
print("合并后: %d  （官方样例新增 %d）\n" % (len(merged), len(added)))

print("=== 官方样例带来的新增 (family, part) ===")
for (fam, part), lst in sorted(added.items()):
    print("  %-30s %-30s x%d" % (fam, part, len(lst)))

print("\n=== 按 family 汇总（合并后）===")
fam = {}
for (f, p), lst in merged.items():
    fam.setdefault(f, []).append(p)
for f in sorted(fam):
    print("  %-30s %2d 个: %s" % (f, len(fam[f]), ", ".join(sorted(fam[f])[:8]) + (" …" if len(fam[f]) > 8 else "")))
