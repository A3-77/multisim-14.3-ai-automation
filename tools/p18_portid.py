# -*- coding: utf-8 -*-
"""P18: 检查 CIITPinSymbolComp@PortID 是否一引脚一端口（重复就会让 %t1==%t2）。

用法: runtime\py32\python.exe tools\p18_portid.py <ms14> <refdes> [<refdes> ...]
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
REFS = sys.argv[2:]
c = msmodel.Circuit.load(SRC)

# CiPort: CiID -> 网络
port_net = {}
for e in c.elements:
    if e.get("Class") == "CiPort":
        inner = list(e)[0]
        nds = [i.get("CiID") for i in inner.findall("Nodes/Item")]
        port_net[e.get("CiID")] = nds
# CiNode: CiID -> 名称
node_name = {}
for e in c.elements:
    if e.get("Class") == "CiNode":
        inner = list(e)[0]
        node_name[e.get("CiID")] = inner.get("LocalName")

# 元件 -> SymCompID
sym_of = {}
for e in c.elements:
    if e.get("Class") == "CiComponent":
        inner = list(e)[0]
        ln = inner.get("LocalName") or ""
        ref = ln.replace("&ASC", "") if ln.startswith("&ASC") else ln
        sym_of[ref] = inner.get("SymCompID")

for ref in REFS:
    sid = sym_of.get(ref)
    print("=" * 58)
    print("%s SymCompID=%s" % (ref, sid))
    if not sid:
        print("  找不到该元件")
        continue
    # 在 Objects 里找 CIITSymbolComp
    for e in c.objects:
        if e.get("ID") != sid:
            continue
        inner = list(e)[0]
        print("  symbol Class=%s" % inner.get("Class"))
        portids = []
        for ps in inner.iter("CIITPinSymbolComp"):
            pid = ps.get("PortID")
            pname = ps.get("PinName") or ps.get("Name") or "?"
            portids.append(pid)
            print("    PinSymbol PinName=%-4s PortID=%-12s -> net=%s"
                  % (pname, pid,
                     [node_name.get(n) for n in port_net.get(pid, [])]))
        cnt = Counter(portids)
        dup = {k: v for k, v in cnt.items() if v > 1}
        print("  PortID 去重: %d/%d  重复=%s" % (len(cnt), len(portids), dup or "无"))
        break
