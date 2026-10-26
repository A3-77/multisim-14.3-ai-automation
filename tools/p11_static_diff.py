# -*- coding: utf-8 -*-
"""P11 静态对比：
1. acceptance.ms14 里 741404072（donor GND 连接器）出现次数 —— 验证重复 ID
2. 克隆 V1 的 CiComponent/CiModel vs donor 原 V2 的差异
"""
import os
import sys
import gzip

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import xml.etree.ElementTree as ET

DONOR = os.path.join(ROOT, "corpus", "samples",
                     "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz")

# ---------- 1. 重复 ID 验证 ----------
raw = open(os.path.join(ROOT, "out", "_accept.xml"), encoding="utf-8").read()
print("=== 1. donor GND 连接器 ID 在 acceptance.ms14 的出现 ===")
for cid in ("741404072", "741408560", "741406712", "741409088"):
    n_def = raw.count('<Item ID="%s"' % cid)
    n_ref = raw.count('ID="%s"' % cid) - n_def
    print("  %s: 定义 %d 处, 引用 %d 处" % (cid, n_def, n_ref))

# ---------- 2. CiComponent / CiModel 对比 ----------
donor = msmodel.Circuit(gzip.open(DONOR, "rb").read())
mine = msmodel.Circuit.from_xml_file(os.path.join(ROOT, "out", "_accept.xml"))

dv = donor.find("V2")
mv = mine.find("V1")
d_comp = donor._item_of(dv["ciid"]).find("CiComponent")
m_comp = mine._item_of(mv["ciid"]).find("CiComponent")

print()
print("=== 2. CiComponent 属性对比 ===")
for k in sorted(set(d_comp.attrib) | set(m_comp.attrib)):
    a, b = d_comp.get(k), m_comp.get(k)
    flag = "" if a == b else "   <<< 不同"
    print("  %-24s donor=%-40s mine=%-40s%s" % (k, a, b, flag))

print()
print("=== 3. Attributes 槽对比（CiComponent 下） ===")
d_attrs = list(d_comp.find("Attributes"))
m_attrs = list(m_comp.find("Attributes"))
print("  槽数: donor=%d mine=%d" % (len(d_attrs), len(m_attrs)))
for i in range(max(len(d_attrs), len(m_attrs))):
    sa = ET.tostring(d_attrs[i], encoding="unicode") if i < len(d_attrs) else "(无)"
    sb = ET.tostring(m_attrs[i], encoding="unicode") if i < len(m_attrs) else "(无)"
    if sa != sb:
        print("  --- 槽 %d 不同 ---" % i)
        print("    donor: %s" % sa[:400])
        print("    mine : %s" % sb[:400])

print()
print("=== 4. CiModel 对比 ===")
d_model = None
for e in donor.elements:
    if e.get("CiID") == d_comp.get("Model"):
        d_model = e
        break
m_model = None
for e in mine.elements:
    if e.get("CiID") == m_comp.get("Model"):
        m_model = e
        break
print("  donor Model CiID=%s  mine Model CiID=%s" % (d_comp.get("Model"), m_comp.get("Model")))
if d_model is not None and m_model is not None:
    di, mi = list(d_model)[0], list(m_model)[0]
    for k in sorted(set(di.attrib) | set(mi.attrib)):
        a, b = di.get(k), mi.get(k)
        flag = "" if a == b else "   <<< 不同"
        print("  %-24s donor=%-40s mine=%-40s%s" % (k, a, b, flag))
    # Model 内容对比
    ds = ET.tostring(d_model, encoding="unicode")
    ms = ET.tostring(m_model, encoding="unicode")
    print("  Model XML 长度: donor=%d mine=%d" % (len(ds), len(ms)))
    if ds != ms:
        # 找第一处差异
        for i in range(min(len(ds), len(ms))):
            if ds[i] != ms[i]:
                print("  首处差异 @%d:" % i)
                print("    donor: ...%s" % ds[max(0, i - 80):i + 120])
                print("    mine : ...%s" % ms[max(0, i - 80):i + 120])
                break
