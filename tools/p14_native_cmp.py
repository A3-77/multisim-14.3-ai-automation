# -*- coding: utf-8 -*-
"""P14i: 原生文件 vs 自建文件的电路级结构对比"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl

FILES = [
    ("buck", r"C:\Users\A377\Downloads\multisim_simulations\aareyes96-multisim_simulations-daff854\buck.ms14"),
    ("donor", os.path.join(ROOT, "out", "donor_spice.ms14")),
    ("accept", os.path.join(ROOT, "out", "ref", "acceptance.ms14")),
]


def sub_tags(el):
    return [(c.tag, c.get("Class") or "", len(list(c))) for c in el]


for label, path in FILES:
    if not os.path.exists(path):
        print("缺失:", path)
        continue
    xml, _ = dcl.read_ms14(path)
    root = ET.fromstring(xml)
    print("=" * 74)
    print(label, os.path.basename(path))
    print("=" * 74)

    # CiCircuit 子结构
    for e in root.iter():
        if e.get("Class") == "CiCircuit":
            inner = list(e)[0] if len(list(e)) else None
            print("CiCircuit CiID=%s 子项:" % e.get("CiID"))
            if inner is not None:
                for tag, cls, n in sub_tags(inner):
                    print("   %-26s %-22s %d" % (tag, cls, n))
            break

    # Extensions 下的扩展
    print("\nExtensions:")
    for i, exts in enumerate(root.iter("Extensions")):
        for ch in exts:
            print("   [%d] %-24s Class=%s 子项=%d" % (i, ch.tag, ch.get("Class") or "-", len(list(ch))))

    # 顶层 tag 概览
    print("\n顶层结构:")
    for ch in root:
        print("   %-30s Class=%-24s 子项=%d" % (ch.tag, ch.get("Class") or "-", len(list(ch))))
    print()
