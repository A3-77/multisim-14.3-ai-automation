# -*- coding: utf-8 -*-
"""逐字段对比 donor(7812) 与克隆(p1_with_probe) 的老式探针对象。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

DONOR = os.path.join(ROOT, "samples", "7812.ms12")
CLONE = os.path.join(ROOT, "out", "p1_with_probe.ms14")


def load(p):
    xml, _ = dcl.read_ms14(p)
    return ET.fromstring(xml)


def grab(t, cls):
    for e in t.iter("Item"):
        if e.get("Class") == cls:
            return e
    return None


td, tc = load(DONOR), load(CLONE)

print("=" * 70)
print("A. 绘图对象 CIITProbeComponent 属性逐项对比")
print("=" * 70)
dd = grab(td, "CIITProbeComponent").find("CIITProbeComponent")
cd = grab(tc, "CIITProbeComponent").find("CIITProbeComponent")
keys = sorted(set(dd.attrib) | set(cd.attrib))
DIFF = []
for k in keys:
    a, b = dd.get(k), cd.get(k)
    mark = "  " if a == b else "→"
    if a != b:
        DIFF.append(k)
    print("  %s %-24s donor=%-28r clone=%r" % (mark, k, a, b))
print("\n  不同的键：%s" % DIFF)

print("\n  子元素结构 donor :", [c.tag for c in dd])
print("  子元素结构 clone :", [c.tag for c in cd])
sd = ET.tostring(dd.find("ConnectList"), encoding="unicode") if dd.find("ConnectList") is not None else None
sc = ET.tostring(cd.find("ConnectList"), encoding="unicode") if cd.find("ConnectList") is not None else None
print("  ConnectList donor:", sd)
print("  ConnectList clone:", sc)

print("\n" + "=" * 70)
print("B. 电气对象 CiProbeComp 属性逐项对比")
print("=" * 70)
de = grab(td, "CiProbeComp").find("CiProbeComp")
ce = grab(tc, "CiProbeComp").find("CiProbeComp")
DIFF2 = []
for k in sorted(set(de.attrib) | set(ce.attrib)):
    a, b = de.get(k), ce.get(k)
    if a != b:
        DIFF2.append(k)
    print("  %s %-20s donor=%-34r clone=%r" % ("  " if a == b else "→", k, a, b))
print("\n  不同的键：%s" % DIFF2)

print("\n  Attributes donor:", ET.tostring(de.find("Attributes"), encoding="unicode")[:400])
print("  Attributes clone:", ET.tostring(ce.find("Attributes"), encoding="unicode")[:400])
print("  Ports donor:", ET.tostring(de.find("Ports"), encoding="unicode"))
print("  Ports clone:", ET.tostring(ce.find("Ports"), encoding="unicode"))

print("\n" + "=" * 70)
print("C. 顶层结构差异（找 donor 有而 clone 没有的）")
print("=" * 70)


def paths(t, limit=6):
    out = {}
    for e in t.iter():
        p = []
        cur = e
        while cur is not None and len(p) < limit:
            p.append(cur.tag if not (cur.get("Class") or cur.get("CiID") or cur.get("ID"))
                     else "%s[%s]" % (cur.tag, cur.get("Class") or cur.get("CiID") or cur.get("ID")))
            cur = None  # ElementTree 无 parent，只取两级
        out["/".join(reversed(p))] = out.get("/".join(reversed(p)), 0) + 1
    return out


import collections
def cls_count(t):
    c = collections.Counter()
    for e in t.iter():
        v = e.get("Class")
        if v:
            c[v] += 1
    return c

cd_, cc_ = cls_count(td), cls_count(tc)
for k in sorted(set(cd_) | set(cc_)):
    if cd_.get(k, 0) != cc_.get(k, 0):
        print("  %-40s donor=%d clone=%d" % (k, cd_.get(k, 0), cc_.get(k, 0)))

print("\n" + "=" * 70)
print("D. donor 的 CiCircuit/Probes 与 Triggers")
print("=" * 70)
for e in td.iter("CiCircuit"):
    s = ET.tostring(e, encoding="unicode")
    i, j = s.find("<Probes"), s.find("</Probes>")
    print("  donor Probes:", s[i:j + 9] if i >= 0 else None)
    break
for e in td.iter():
    if "Trigger" in (e.get("Class") or ""):
        print("  donor trigger 节点:", e.tag, dict(e.attrib))
for e in tc.iter():
    if "Trigger" in (e.get("Class") or ""):
        print("  clone trigger 节点:", e.tag, dict(e.attrib))
print("  clone 有 TotalProbeTriggers 吗:",
      any("Trigger" in (e.get("Class") or "") for e in tc.iter()))
