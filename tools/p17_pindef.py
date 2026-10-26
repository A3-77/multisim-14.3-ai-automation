# -*- coding: utf-8 -*-
"""P17: 查 CODPinComp 引脚定义的 ConnectList 里到底列了什么（类名分布）。

官方文件里连通性可能只存在「引脚侧」：pin def -> ConnectList -> 导线 / 连接器。
本脚本统计这些 Item 指向的类，并打印几个实例。

用法: runtime\py32\python.exe tools\p17_pindef.py <ms14> [实例数]
"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 4
c = msmodel.Circuit.load(SRC)

idcls = {}
for e in c.tree.iter():
    for k in ("ID", "CiID"):
        v = e.get(k)
        if v:
            idcls.setdefault(v, e.get("Class") or e.tag)

# CODPinComp 有两种：带子元素的「定义」和自闭合的「引用」
defs, refs = [], []
for e in c.tree.iter("Item"):
    if e.get("Class") != "CODPinComp":
        continue
    (defs if len(list(e)) else refs).append(e)
print("%s: CODPinComp 定义=%d 引用=%d" % (os.path.basename(SRC), len(defs), len(refs)))

stat = Counter()
detail = []
for d in defs:
    cl = d.find("ConnectList")
    if cl is None:
        stat[("<无 ConnectList>",)] += 1
        continue
    ids = [it.get("ID") for it in cl.findall("Item")]
    if not ids:
        stat[("<空 ConnectList>",)] += 1
        continue
    kinds = tuple(sorted({idcls.get(i, "<未注册>") for i in ids}))
    stat[kinds] += 1
    if len(detail) < N:
        detail.append((d.get("ID"), ids, kinds))

print("\nConnectList 指向类型组合分布:")
for k, v in stat.most_common(12):
    print("   %-60s %d" % (",".join(k), v))

print("\n实例:")
for did, ids, kinds in detail:
    print("  pin def %s -> %s" % (did, list(zip(ids, kinds))))
    inner = d = None
