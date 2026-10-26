# -*- coding: utf-8 -*-
"""导出 7812.ms12 里老式探针的完整 XML 结构。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SRC = os.path.join(ROOT, "samples", "7812.ms12")
OUT = os.path.join(ROOT, "out", "probe_legacy_dump.xml")

xml, info = dcl.read_ms14(SRC)
print("解出 %d 字节, 头部 %s" % (len(xml), info))
open(os.path.join(ROOT, "out", "p1_7812_plain.xml"), "wb").write(xml)
t = ET.fromstring(xml)

# 1) 绘图对象 CIITProbeComponent
for e in t.iter("Item"):
    if e.get("Class") == "CIITProbeComponent":
        s = ET.tostring(e, encoding="unicode")
        print("\n" + "=" * 70)
        print("### CIITProbeComponent (绘图对象) len=%d" % len(s))
        print("=" * 70)
        print(s)

# 2) 电气对象 CiProbeComp
for e in t.iter("Item"):
    if e.get("Class") == "CiProbeComp":
        s = ET.tostring(e, encoding="unicode")
        print("\n" + "=" * 70)
        print("### CiProbeComp (电气对象) len=%d" % len(s))
        print("=" * 70)
        print(s)

# 3) CiCircuit 的 Probes 段
for e in t.iter("CiCircuit"):
    s = ET.tostring(e, encoding="unicode")
    i = s.find("<Probes")
    j = s.find("</Probes>")
    print("\n" + "=" * 70)
    print("### CiCircuit/Probes")
    print("=" * 70)
    print(s[max(0, i - 200):j + 9] if i >= 0 else "(没有 Probes 段)")
    break

# 4) 全部相关 class 统计
import collections
cnt = collections.Counter()
for e in t.iter():
    c = e.get("Class")
    if c and ("Probe" in c or "Meter" in c):
        cnt[c] += 1
print("\n### 探针相关 class:", dict(cnt))
