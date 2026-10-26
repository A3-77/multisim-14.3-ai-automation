# -*- coding: utf-8 -*-
"""P13-B：找非虚拟电阻做对照（7812 样本），并逐字节比对 donor 原 R1 vs 克隆 R1。"""
import os
import sys
import re
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

print("=== 1. 7812 样本里的电阻 ===")
p7812 = os.path.join(ROOT, "samples", "7812.ms12")
try:
    c7 = msmodel.Circuit.load(p7812)
    for comp in c7.components():
        if "RESIST" in (comp["family"] or "").upper():
            print("  %-5s family=%-12s part=%-20s params=%s"
                  % (comp["refdes"], comp["family"], comp["part"],
                     c7.params(comp["comp"])[:4]))
except Exception as e:
    print("  7812 读不了:", repr(e))

print()
print("=== 2. donor_spice 原 R1 vs p13_a3 克隆 R1 逐槽比对（ID 归一化）===")
d = msbuild.load_donor(os.path.join(ROOT, "out", "donor_spice.ms14"))
m = msmodel.Circuit.load(os.path.join(ROOT, "out", "p13_a3.ms14"))

dc = d.find("R1")
mc = m.find("R1")
di = dc["comp"]
mi = mc["comp"]

ID_RE = re.compile(r'("(?:CiID|ID|SymCompID|InstanceID|Circuit|Model|PortID)"\s*=\s*")[^"]*(")')


def norm(el):
    s = ET.tostring(el, encoding="unicode")
    return ID_RE.sub(r"\1<ID>\2", s)


print("  CiComponent 属性（归一化）:")
for k in sorted(set(di.attrib) | set(mi.attrib)):
    a, b = di.get(k), mi.get(k)
    if k in ("InstanceID", "SymCompID", "Model", "Circuit"):
        a = b = "<ID>"
    if a != b:
        print("    %-14s donor=%-24r mine=%r" % (k, a, b))

da, ma = list(di.find("Attributes")), list(mi.find("Attributes"))
print("  槽数 donor=%d mine=%d" % (len(da), len(ma)))
diff = 0
for i in range(max(len(da), len(ma))):
    sa = norm(da[i]) if i < len(da) else "(无)"
    sb = norm(ma[i]) if i < len(ma) else "(无)"
    if sa != sb:
        diff += 1
        print("  --- 槽 %d ---" % i)
        print("    donor: %s" % sa[:400].replace("\n", " "))
        print("    mine : %s" % sb[:400].replace("\n", " "))
print("  差异槽数: %d" % diff)

print()
print("=== 3. 参数列表全量（含空 Item）===")
for label, comp in (("donor", di), ("mine", mi)):
    pl = list(comp.find("Attributes"))[2].find("CiaParamList")
    ds = pl.find("doubles")
    print("  %-6s doubles=%d 值=%s" % (label, len(list(ds)),
          [x.get("Value") for x in ds]))
    ps = pl.find("parameters")
    print("         parameters=%s" % ([x.get("Value") for x in ps] if ps is not None else None))
