# -*- coding: utf-8 -*-
"""P18: 对比 CiCircuit 的子节点结构（有哪些节、各节里有多少项）。

Multisim 载入时按 CiCircuit 的子节重建内部模型。少一节 → 内部模型不完整。

用法: runtime\py32\python.exe tools\p18_circuit.py <ms14> [<ms14> ...]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

for src in sys.argv[1:]:
    c = msmodel.Circuit.load(src)
    print("=" * 62)
    print(os.path.basename(src))
    for e in c.elements:
        if e.get("Class") != "CiCircuit":
            continue
        inner = list(e)[0]
        print("  CiCircuit CiID=%s 属性=%s" % (e.get("CiID"), list(inner.attrib.keys())))
        for ch in inner:
            n = len(list(ch))
            tag = ch.tag
            print("    %-22s 子项=%-4d" % (tag, n))
            if tag in ("Components", "Ports", "Nodes", "Probes", "ProbeExts", "Models"):
                ids = [i.get("CiID") for i in ch.findall("Item")][:6]
                if ids:
                    print("        示例: %s" % ids)
        break
