# -*- coding: utf-8 -*-
"""验证：引脚绝对坐标 = 引脚符号的变换矩阵 × 局部连接点。

并与 ReferencedComponents 里的 CODPinComp 定义交叉核对。
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

P = os.path.join(ROOT, "out", "samples",
                 "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.ms14")

c = msmodel.Circuit.from_xml_file(P)
r = ET.parse(P).getroot()
d = r.find(".//CIITDiagram")

# CODPinComp 定义表：ID -> (x, y)
defs = {}
for it in d.find("Components/CODComposite/ReferencedComponents"):
    inner = list(it)
    if inner and inner[0].get("Class") == "CODPinComp":
        defs[it.get("ID")] = (float(inner[0].get("CenterX")),
                              float(inner[0].get("CenterY")))
print("引脚定义 %d 个" % len(defs))

ok = bad = 0
for comp in c.components():
    item = c.symbol_of(comp["ciid"])
    if item is None:
        continue
    for pin in item.iter("CIITPinSymbolComp"):
        conn = pin.find(".//CIITPinConnectorComp")
        if conn is None:
            continue
        lx, ly = float(conn.get("ptCenterX")), float(conn.get("ptCenterY"))
        m = [float(pin.get("Transformer-M%d%d" % (i, j))) for i in range(2) for j in range(2)]
        tx, ty = float(pin.get("Transformer-M20")), float(pin.get("Transformer-M21"))
        x = m[0] * lx + m[2] * ly + tx
        y = m[1] * lx + m[3] * ly + ty
        refs = [i.get("ID") for i in conn.findall(".//ConnectList/Item")]
        got = [defs.get(i) for i in refs]
        name = (pin.get("PinName") or "").replace("&ASC", "")
        match = any(g is not None and abs(g[0] - x) < 1.5 and abs(g[1] - y) < 1.5
                    for g in got)
        if match:
            ok += 1
        else:
            bad += 1
            print("  不匹配 %-4s pin%s 计算=(%.0f,%.0f) 定义=%s refs=%s"
                  % (comp["refdes"], name, x, y, got, refs))
print("坐标公式: 匹配 %d / 不匹配 %d" % (ok, bad))
