# -*- coding: utf-8 -*-
"""P18: 对比某元件符号内部各对象的坐标 —— 判断导线是否真的落在引脚上。

Multisim 的 SPICE 网表按**绘图几何**判定导线是否接到引脚。若引脚定义
（CODPinComp.CenterX/CenterY）与符号变换（CIITPinSymbolComp/CIITPinConnectorComp
的 Transformer-M20/M21）推出的位置不一致，导线就接不上。

用法: runtime\py32\python.exe tools\p18_geom.py <ms14> <refdes>
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC, REF = sys.argv[1], sys.argv[2]
c = msmodel.Circuit.load(SRC)

sym_of = {}
for e in c.elements:
    if e.get("Class") == "CiComponent":
        inner = list(e)[0]
        ln = (inner.get("LocalName") or "").replace("&ASC", "")
        sym_of[ln] = inner.get("SymCompID")

sid = sym_of.get(REF)
print("%s %s SymCompID=%s" % (os.path.basename(SRC), REF, sid))
if not sid:
    raise SystemExit("找不到")

for e in c.objects:
    if e.get("ID") != sid:
        continue
    inner = list(e)[0]
    top = inner.get("Transformer-M20"), inner.get("Transformer-M21")
    print("  符号顶层 Transformer-M20/M21 = %s/%s" % top)
    for el in inner.iter():
        cls = el.get("Class")
        if not cls:
            continue
        m20, m21 = el.get("Transformer-M20"), el.get("Transformer-M21")
        cx, cy = el.get("CenterX"), el.get("CenterY")
        if m20 is not None or cx is not None:
            print("    %-24s ID=%-12s M20/M21=%-8s/%-8s Center=(%s,%s) PortID=%s PinName=%s"
                  % (cls, el.get("ID"), m20, m21, cx, cy,
                     el.get("PortID"), (el.get("PinName") or "").replace("&ASC", "")))
    break

# 引脚定义（Objects 里的 CODPinComp 定义，按 ConnectList 指向的 CIITPinConnectorComp 找）
print("  -- 该符号里的 CIITPinConnectorComp 定义:")
for e in c.objects:
    inner = list(e)
    if not inner or inner[0].get("Class") != "CIITPinConnectorComp":
        continue
    d = inner[0]
    print("    ID=%s M20/M21=%s/%s"
          % (e.get("ID"), d.get("Transformer-M20"), d.get("Transformer-M21")))
