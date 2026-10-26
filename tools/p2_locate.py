# -*- coding: utf-8 -*-
"""定位 7812 里各类关联结构的确切父路径，为删除做准备。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import xml.etree.ElementTree as ET  # noqa: E402

t = ET.parse(os.path.join(ROOT, "out", "rev_base.xml")).getroot()


def path_of(e):
    """从根到该元素的标签路径（ElementTree 无 parent，用递归预计算）。"""
    parent = {}
    for p in t.iter():
        for c in p:
            parent[c] = p
    chain = []
    cur = e
    while cur is not None:
        cls = cur.get("Class") or cur.get("CiID") or cur.get("ID")
        chain.append("%s%s" % (cur.tag, "[%s]" % cls if cls else ""))
        cur = parent.get(cur)
    return "/".join(reversed(chain))


# 1) 自闭合的 CIITProbeComponent 引用在哪
print("=== 自闭合 CIITProbeComponent / CiProbeComp 引用位置 ===")
for e in t.iter("Item"):
    cls = e.get("Class")
    if cls in ("CIITProbeComponent", "CiProbeComp") and len(list(e)) == 0:
        print("  %-24s ID=%-10s CiID=%-10s  路径=%s"
              % (cls, e.get("ID"), e.get("CiID"), path_of(e)[:150]))

# 2) CSchDesignNetLabel 在哪
print("\n=== CSchDesignNetLabel 位置 ===")
seen = set()
for e in t.iter():
    if e.get("Class") == "CSchDesignNetLabel":
        p = path_of(e)
        key = p.split("/")[-2] if "/" in p else p
        if key not in seen:
            seen.add(key)
            print("  父路径:", p[:170])
            print("  属性:", dict(e.attrib))

# 3) CODNodeTextComp 在哪
print("\n=== CODNodeTextComp 位置（前3个） ===")
n = 0
for e in t.iter():
    if e.get("Class") == "CODNodeTextComp":
        print("  路径:", path_of(e)[:170])
        print("  属性:", dict(e.attrib))
        n += 1
        if n >= 3:
            break

# 4) RefDesMgr 结构
print("\n=== RefDesMgrs 结构 ===")
for e in t.iter():
    if e.tag in ("RefDesMgrs", "RefDesMgr", "RefDesPrefixUsageMap", "RefDesPrefixUsage",
                 "ComponentPins", "ERC_CHK_OPTIONS", "TotalProbeTriggers"):
        print("  %-24s Class=%-32s 子=%d 属性=%s"
              % (e.tag, e.get("Class"), len(list(e)),
                 {k: v for k, v in list(e.attrib.items())[:3]}))

# 5) Elements 下每个 Item 的 Class + 是否被 CiCircuit 引用
print("\n=== Elements 下 36 个 Item 一览 ===")
circuit_refs = set()
for e in t.iter("CiCircuit"):
    for tag in ("Models", "Nodes", "Probes", "Components"):
        nd = e.find(tag)
        if nd is not None:
            for i in nd:
                circuit_refs.add(i.get("CiID"))
for i, e in enumerate(t.find(".//Elements")):
    cls = e.get("Class")
    ciid = e.get("CiID")
    inref = "✓" if ciid in circuit_refs else " "
    inner = list(e)
    subtags = []
    if inner:
        for c in inner[0].iter():
            if c.tag != inner[0].tag:
                subtags.append(c.tag)
        subtags = subtags[:4]
    print("  [%2d] %s %-16s CiID=%-10s 子=%s" % (i, inref, cls, ciid, subtags))

# 6) Objects 下 21 个 Item
print("\n=== Components/CODComposite/Objects 下 21 个 Item ===")
objs = t.find(".//Components/CODComposite/Objects")
for i, e in enumerate(objs):
    inner = list(e)
    cls = inner[0].get("Class") if inner else "(空)"
    owner = inner[0].get("CiComponent") if inner else None
    print("  [%2d] ID=%-10s %-24s CiComponent=%s" % (i, e.get("ID"), cls, owner))
