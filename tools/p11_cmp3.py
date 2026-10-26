# -*- coding: utf-8 -*-
"""P11 三方字段对比：donor_spice 原 V2 / p10 的 V2 / acceptance 的 V1。

对每个源 dump：
  - CiComponent 全部属性
  - Attributes 每个槽的 XML
  - CiModel 全部属性 + XML
只打印三方有差异的项。
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = [
    ("donor", os.path.join(ROOT, "out", "_donor_spice.xml"), "V2"),
    ("p10", os.path.join(ROOT, "out", "_p10.xml"), "V2"),
    ("accept", os.path.join(ROOT, "out", "_accept.xml"), "V1"),
]

data = {}
for label, path, ref in SRC:
    c = msmodel.Circuit.from_xml_file(path)
    comp = c.find(ref)
    item = c._item_of(comp["ciid"])
    inner = item.find("CiComponent")
    model = None
    for e in c.elements:
        if e.get("CiID") == inner.get("Model"):
            model = e
            break
    attrs = []
    at = inner.find("Attributes")
    if at is not None:
        attrs = [ET.tostring(x, encoding="unicode") for x in at]
    data[label] = {
        "comp_attrib": dict(inner.attrib),
        "comp_children": [ch.tag for ch in inner if ch.tag != "Attributes"],
        "attrs": attrs,
        "model_attrib": dict(list(model)[0].attrib) if model is not None else None,
        "model_xml": ET.tostring(model, encoding="unicode") if model is not None else None,
        "ports": [p for p in c.ports() if p["component"] == comp["ciid"]],
        "pos": c.position(comp["ciid"]),
    }

labels = [s[0] for s in SRC]

print("=" * 78)
print("1. CiComponent 属性")
print("=" * 78)
keys = set()
for d in data.values():
    keys |= set(d["comp_attrib"])
for k in sorted(keys):
    vals = [data[l]["comp_attrib"].get(k) for l in labels]
    if len(set(vals)) > 1:
        print("  %-22s" % k)
        for l, v in zip(labels, vals):
            print("      %-8s %r" % (l, v))
print("  （未列出的属性三方一致）")

print()
print("2. CiComponent 子节点顺序")
for l in labels:
    print("  %-8s %s" % (l, data[l]["comp_children"]))

print()
print("=" * 78)
print("3. Attributes 槽位（只打印差异）")
print("=" * 78)
n = max(len(data[l]["attrs"]) for l in labels)
print("  槽数: " + ", ".join("%s=%d" % (l, len(data[l]["attrs"])) for l in labels))
for i in range(n):
    vals = [data[l]["attrs"][i] if i < len(data[l]["attrs"]) else "(无)" for l in labels]
    if len(set(vals)) > 1:
        print()
        print("  --- 槽 %d ---" % i)
        for l, v in zip(labels, vals):
            print("    %-8s %s" % (l, v[:700]))

print()
print("=" * 78)
print("4. CiModel")
print("=" * 78)
for l in labels:
    print("  %-8s attrib=%s" % (l, data[l]["model_attrib"]))
    x = data[l]["model_xml"] or ""
    print("  %-8s xml_len=%d" % (l, len(x)))
    print("           head=%s" % x[:300].replace("\n", " "))
mx = [data[l]["model_xml"] for l in labels]
if len(set(mx)) > 1:
    print("  ** CiModel XML 不一致 **")
else:
    print("  CiModel XML 完全一致（除 CiID 外需逐字比对见下）")

print()
print("=" * 78)
print("5. 端口")
print("=" * 78)
for l in labels:
    print("  %-8s %s" % (l, [(p["name"], p["ciid"]) for p in data[l]["ports"]]))
print("  pos:", {l: data[l]["pos"] for l in labels})
