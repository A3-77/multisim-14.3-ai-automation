# -*- coding: utf-8 -*-
"""P17: 类名普查 —— 列出文件里所有 Class 属性的取值及出现次数，用于做差集。

buck.ms14 已证实可仿真（V(PR1)=59.9487V）。凡 buck 有、生成件没有的类，
就是「缺失结构」的候选。

用法: runtime\py32\python.exe tools\p17_census.py <ms14> [<ms14> ...]
"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

sets = {}
for src in sys.argv[1:]:
    c = msmodel.Circuit.load(src)
    cls = Counter()
    tags = Counter()
    for e in c.tree.iter():
        tags[e.tag] += 1
        v = e.get("Class")
        if v:
            cls[v] += 1
    sets[src] = (cls, tags)
    print("%-34s Class 种类=%-3d 元素总数=%d" % (os.path.basename(src), len(cls), sum(tags.values())))

allc = set()
for _, (cls, _t) in sets.items():
    allc |= set(cls)

print("\n=== Class 出现矩阵（按 buck 里是否有排序）===")
hdr = "%-42s" % "Class"
for s in sets:
    hdr += "%16s" % os.path.basename(s)[:15]
print(hdr)
for k in sorted(allc, key=lambda x: (-sets[list(sets)[0]][0].get(x, 0), x)):
    line = "%-42s" % k
    for s in sets:
        line += "%16d" % sets[s][0].get(k, 0)
    print(line)

print("\n=== 只在第一个文件里出现的 Class ===")
first = list(sets)[0]
for k in sorted(sets[first][0]):
    if all(sets[s][0].get(k, 0) == 0 for s in list(sets)[1:]):
        print("   ", k, sets[first][0][k])
