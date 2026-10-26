# -*- coding: utf-8 -*-
"""P15b: 元件对象图可达性遍历 —— buck R1 vs 我的 R1，比对象类型多重集"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

ID_ATTRS = ("CiID", "ID", "Component", "Circuit", "SymCompID", "CiProbeComp",
            "CiProbeExtComp", "Scope", "Model", "Node", "Connect1", "Connect2",
            "PortID", "CiComponent")


def walk(path, refdes, label):
    c = msmodel.Circuit.from_xml_file(path)
    ciid = c.find(refdes)["ciid"]

    # 建索引：所有带 ID/CiID 的元素
    index = {}
    for el in c.tree.iter():
        for a in ("CiID", "ID"):
            v = el.get(a)
            if v and v.isdigit():
                index.setdefault(v, el)

    seen = set()
    queue = [ciid]
    classes = Counter()
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        el = index.get(cur)
        if el is None:
            classes["<悬空:%s>" % cur] += 1
            continue
        cls = el.get("Class") or el.tag
        classes[cls] += 1
        for e2 in el.iter():
            for a in ID_ATTRS:
                v = e2.get(a)
                if v and v.isdigit() and v not in seen:
                    queue.append(v)

    print("=" * 70)
    print("%s / %s  可达对象 %d 个" % (label, refdes, len(seen)))
    print("=" * 70)
    for k, v in sorted(classes.items()):
        print("   %-36s %d" % (k, v))
    return classes


a = walk(os.path.join(ROOT, "out", "_p14_buck.xml"), "R1", "buck")
b = walk(os.path.join(ROOT, "out", "_p15_div.xml"), "R1", "mine")

print()
print("=" * 70)
print("差异（buck 有 / 我没有）")
print("=" * 70)
for k in sorted(set(a) | set(b)):
    if a.get(k, 0) != b.get(k, 0):
        print("   %-36s buck=%-4d mine=%-4d" % (k, a.get(k, 0), b.get(k, 0)))
