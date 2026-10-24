# -*- coding: utf-8 -*-
"""测试：把接地符号从样例克隆进空白电路，看 Multisim 是否渲染。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

DONOR = os.path.join(ROOT, "out", "samples",
                     "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.ms14")

donor = msmodel.Circuit.from_xml_file(DONOR)
for ref in ("V2", "R1"):
    d = msbuild.Donor(donor, ref)
    print(ref, d.describe())

gnds = [c for c in donor.components() if c["part"] == "GROUND"]
print("接地数", len(gnds))

# 用第一个接地做模板
gnd_comp = gnds[0]
a = msbuild.Assembler()
g = msbuild.Donor(donor, gnd_comp["refdes"])
print("接地模板", g.describe())

ciid, ports = a.add(g, x=400.0, y=300.0)
print("新增接地 CiID", ciid, "引脚", ports)

out = os.path.join(ROOT, "out", "test_gnd.ms14")
n, body = a.save(out)
print("写出", out, n, "字节")
print("回读组件:", [x["refdes"] for x in msmodel.Circuit.load(out).components()])
