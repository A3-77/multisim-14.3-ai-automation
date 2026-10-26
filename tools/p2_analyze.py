# -*- coding: utf-8 -*-
"""分析 7812.ms12 的完整结构：元件 -> 引脚 -> 模型 -> 绘图对象 -> 导线 -> 网络 -> 全局登记。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SRC = os.path.join(ROOT, "samples", "7812.ms12")
PLAIN = os.path.join(ROOT, "out", "rev_base.xml")

xml, info = dcl.read_ms14(SRC)
open(PLAIN, "wb").write(xml)
print("明文已存 %s（%d 字节）" % (PLAIN, len(xml)))

t = ET.fromstring(xml)
diagram = t.find(".//CIITDiagram")
print("CIITDiagram 直接子元素:", [c.tag for c in diagram])

# --- 顶层结构（非 Elements / Components）---
print("\n=== CIITDiagram 直属子元素明细 ===")
for c in diagram:
    cls = c.get("Class") or c.get("CiID") or c.get("ID") or ""
    n = len(list(c))
    print("  %-28s Class=%-34s 子元素=%d" % (c.tag, cls, n))

# --- Elements 里各类对象数量 ---
import collections
cnt = collections.Counter()
for e in t.iter("Item"):
    if e.get("Class"):
        cnt[e.get("Class")] += 1
print("\n=== Elements/Item Class 统计 ===")
for k, v in sorted(cnt.items()):
    print("  %-30s %d" % (k, v))

# --- Components/CODComposite 下有什么 ---
print("\n=== Components/CODComposite 子元素 ===")
for c in diagram.find("Components/CODComposite"):
    print("  %-28s 子元素=%d" % (c.tag, len(list(c))))

# --- 元件 -> 引脚 -> 节点 关系 ---
print("\n=== 元件与引脚 ===")
comp_ports = {}
for e in t.iter("Item"):
    if e.get("Class") == "CiPort":
        p = e.find("CiPort")
        comp_ports.setdefault(p.get("Component"), []).append(e.get("CiID"))

for e in t.iter("Item"):
    if e.get("Class") == "CiComponent":
        c = e.find("CiComponent")
        at = c.find("Attributes")
        items = list(at) if at is not None else []
        fam = part = ""
        if len(items) > 4:
            for cs in items[4].iter("CiaCollString"):
                vals = [x.get("Value") or "" for x in cs.iter("Item")]
                vals = [v.replace("&ASC", "") for v in vals if v.strip()]
                if vals:
                    fam, part = vals[0], (vals[1] if len(vals) > 1 else "")
                    break
        ports = comp_ports.get(e.get("CiID"), [])
        model = c.get("Model")
        sym = c.get("SymCompID")
        print("  %-6s %-20s %-24s CiID=%-10s Model=%-10s Sym=%-10s ports=%d"
              % ((c.get("LocalName") or "").replace("&ASC", ""), fam, part,
                 e.get("CiID"), model, sym, len(ports)))

# --- CiNode -> Ports ---
print("\n=== CiNode ===")
node_ports = {}
for e in t.iter("Item"):
    if e.get("Class") == "CiNode":
        n = e.find("CiNode")
        ps = [i.get("CiID") for i in n.find("Ports")]
        node_ports[e.get("CiID")] = ((n.get("LocalName") or "").replace("&ASC", ""), ps)
        print("  CiID=%-10s name=%-6s ports=%s" % (e.get("CiID"),
                                                  (n.get("LocalName") or "").replace("&ASC", ""), ps))

# --- CiModel ---
print("\n=== CiModel ===")
for e in t.iter("Item"):
    if e.get("Class") == "CiModel":
        m = e.find("CiModel")
        print("  CiID=%-10s Scope=%-10s LocalName=%r" % (
            e.get("CiID"), m.get("Scope"), (m.get("LocalName") or "")[:40]))

# --- 谁引用 CiModel ---
print("\n=== CiCircuit/Models ===")
for e in t.iter("CiCircuit"):
    for tag in ("Models", "Nodes", "Probes", "Components"):
        nd = e.find(tag)
        if nd is not None:
            print("  %-12s %s" % (tag, [i.get("CiID") for i in nd]))
    break
