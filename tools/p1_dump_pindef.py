# -*- coding: utf-8 -*-
"""dump 老式探针的引脚定义（CODPinComp）与 triggers，以及它们被谁引用。"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import xml.etree.ElementTree as ET  # noqa: E402

t = ET.parse(os.path.join(ROOT, "out", "p1_7812_plain.xml")).getroot()

WANT_DEF = {"94236440", "94009296"}
WANT_DRAW = {"96255360"}
WANT_ELEC = {"94162368"}

print("=== 1) ReferencedComponents 里的 CODPinComp 定义 ===")
rc = t.find(".//CODComposite/ReferencedComponents")
print("ReferencedComponents 子元素数:", len(list(rc)) if rc is not None else 0)
for it in (rc if rc is not None else []):
    i = it.get("ID")
    inner = list(it)
    if inner and inner[0].get("Class") == "CODPinComp":
        if i in WANT_DEF:
            print("  ★ %s -> %s" % (i, dict(inner[0].attrib)))

print("\n=== 2) 探针绘图/电气对象被谁引用 ===")
d = open(os.path.join(ROOT, "out", "p1_7812_plain.xml"), encoding="utf-8").read()
for tok in sorted(WANT_DRAW | WANT_ELEC | WANT_DEF):
    print("  %-10s 出现 %d 次" % (tok, d.count(tok)))

print("\n=== 3) InstProbeTriggers / CProbeTriggers ===")
for e in t.iter():
    cls = e.get("Class") or ""
    if "ProbeTrigger" in cls or "Trigger" in cls:
        s = ET.tostring(e, encoding="unicode")
        if len(s) < 3000:
            print("  --- %s (len %d)" % (cls, len(s)))
            print("  " + s.replace("\n", "\n  ")[:2500])
        else:
            print("  --- %s (len %d, 太大，略)" % (cls, len(s)))

print("\n=== 4) 7812 的 CiNode 名 -> CiID 映射（找 net4） ===")
for e in t.iter("Item"):
    if e.get("Class") == "CiNode":
        n = e.find("CiNode")
        print("  CiID=%-10s LocalName=%r ports=%s" % (
            e.get("CiID"), n.get("LocalName"),
            [i.get("CiID") for i in n.find("Ports")]))

print("\n=== 5) 7812 的元件清单 ===")
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
        print("  %-8s %-22s %-28s CiID=%s" % (
            (c.get("LocalName") or "").replace("&ASC", ""), fam, part, e.get("CiID")))
