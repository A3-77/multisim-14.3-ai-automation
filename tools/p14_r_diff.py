# -*- coding: utf-8 -*-
"""P14: 原始 R1 vs 克隆 R1 的完整对象图逐槽比对（ID 归一化）"""
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

DONOR = os.path.join(ROOT, "out", "donor_spice.ms14")
MINE = os.path.join(ROOT, "out", "ref", "acceptance.ms14")

IDRE = re.compile(r"\b\d{6,}\b")


def norm(el):
    """把 XML 里所有长数字 ID 归一化成 #，方便逐槽对比"""
    s = ET.tostring(el, encoding="unicode")
    s = IDRE.sub("#", s)
    s = re.sub(r">\s+<", "><", s)
    return s


def attrs_slots(comp):
    """把 Attributes 的 53 个槽转成可读列表"""
    out = []
    at = comp.find("Attributes")
    if at is None:
        return out
    for i, slot in enumerate(list(at)):
        tag = slot.tag
        inner = list(slot)
        if tag == "CiaParamList" and inner:
            pl = inner[0]
            nums = [x.get("Value") for x in pl.find("doubles").findall("Item")] if pl.find("doubles") is not None else []
            ps = [x.get("Value") for x in pl.find("parameters").findall("Item")] if pl.find("parameters") is not None else []
            out.append((i, tag, "doubles=%s params=%s" % (nums, ps)))
        elif tag == "CiaCString":
            out.append((i, tag, repr(inner[0].get("Value") if inner else "")))
        elif tag == "CiaDOUBLE":
            out.append((i, tag, inner[0].get("Value") if inner else ""))
        else:
            out.append((i, tag, "%d 子项" % len(inner)))
    return out


def graph(path, refdes, label):
    xml, _ = dcl.read_ms14(path)
    open(os.path.join(ROOT, "out", "_p14_%s.xml" % label), "wb").write(xml)
    c = msmodel.Circuit.from_xml_file(os.path.join(ROOT, "out", "_p14_%s.xml" % label))
    comp = c.find(refdes)
    ciid = comp["ciid"]
    item = c._item_of(ciid)
    inner = item.find("CiComponent")

    print("=" * 70)
    print("%s  %s  CiID=%s  part=%s" % (label, refdes, ciid, comp["part"]))
    print("=" * 70)

    # 1) CiComponent 直接子元素 + 关键属性
    print("\n-- CiComponent 属性 --")
    for k in sorted(inner.attrib):
        print("   %-22s %s" % (k, inner.get(k)))

    # 2) Attributes 逐槽
    print("\n-- Attributes 槽（非空/关键） --")
    for i, tag, val in attrs_slots(inner):
        if tag == "CiaParamList" or (val not in ("''", "", "0 子项")):
            print("   [%2d] %-14s %s" % (i, tag, val))

    # 3) CiModel
    mid = inner.get("Model")
    print("\n-- CiModel (CiID=%s) --" % mid)
    m = c._item_of(mid) if mid else None
    if m is not None:
        print(norm(m)[:1200])
    else:
        print("   !! 找不到 CiModel")

    # 4) 端口
    ports_el = inner.find("Ports")
    pids = [x.get("CiID") for x in ports_el.findall("Item")] if ports_el is not None else []
    print("\n-- Ports --")
    for pid in pids:
        p = c._item_of(pid)
        pin = p.find("CiPort") if p is not None else None
        if pin is None:
            print("   %s !! 缺失" % pid)
            continue
        print("   %s LocalName=%s Component=%s Nodes=%s" % (
            pid, pin.get("LocalName"), pin.get("Component"),
            [n.get("CiID") for n in pin.find("Nodes").findall("Item")] if pin.find("Nodes") is not None else []))
    return c, ciid


cd, dci = graph(DONOR, "R1", "donor")
cm, mci = graph(MINE, "R1", "mine")

# 5) 归一化全量 diff
print("\n" + "=" * 70)
print("归一化 diff（CiComponent 全量）")
print("=" * 70)
a = norm(cd._item_of(dci)).replace("\n", "")
b = norm(cm._item_of(mci)).replace("\n", "")
if a == b:
    print("  CiComponent 归一化后完全一致")
else:
    print("  donor: %s" % a[:1500])
    print("  mine : %s" % b[:1500])
