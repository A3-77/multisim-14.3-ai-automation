# -*- coding: utf-8 -*-
"""P17: 检查导线的 Connect1/Connect2 指向什么类的对象。

SPICE 网表 = CIITLinkComp.Connect1/Connect2 -> CODPinComp -> ConnectList
             -> CIITPinConnectorComp（符号内部）
若 Connect1/2 指向的不是 CODPinComp，链路就断了。

用法: runtime\py32\python.exe tools\p17_wire_refs.py <ms14> [数量]
"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 8
c = msmodel.Circuit.load(SRC)

# 全局 ID -> Class 索引
idcls = {}
for e in c.tree.iter():
    for k in ("ID", "CiID"):
        v = e.get(k)
        if v:
            idcls.setdefault(v, e.get("Class") or e.tag)

wires = [e for e in c.tree.iter("Item")
         if e.get("Class") == "CIITLinkComp"]
print("%s: 导线 %d 根" % (os.path.basename(SRC), len(wires)))

stat = Counter()
for w in wires:
    inner = list(w)[0] if list(w) else w
    c1 = inner.get("Connect1") or ""
    c2 = inner.get("Connect2") or ""
    k = (idcls.get(c1, "<空>" if not c1 else "<未注册>"),
         idcls.get(c2, "<空>" if not c2 else "<未注册>"))
    stat[k] += 1
print("Connect1/Connect2 指向类型分布:")
for k, v in stat.most_common():
    print("   %-26s %-26s  %d" % (k[0], k[1], v))

print("\n前 %d 根明细:" % N)
for w in wires[:N]:
    inner = list(w)[0] if list(w) else w
    pts = [(p.get("X"), p.get("Y")) for p in inner.find("Points")]
    print("  wire %s Node=%s NodeText=%s" % (w.get("ID"), inner.get("Node"),
                                             inner.get("NodeText")))
    print("      pts=%s" % (pts,))
    for tag in ("Connect1", "Connect2"):
        v = inner.get(tag) or ""
        print("      %s=%s -> %s" % (tag, v, idcls.get(v, "<空>" if not v else "<未注册>")))
