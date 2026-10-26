# -*- coding: utf-8 -*-
"""P14k: buck(原生可跑) vs donor vs mine 的引脚定义本体对比"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

FILES = [
    ("buck", os.path.join(ROOT, "out", "_p14_buck.xml"), "R1"),
    ("donor", os.path.join(ROOT, "out", "_p14_donor.xml"), "R1"),
    ("mine", os.path.join(ROOT, "out", "_p14_mine.xml"), "R1"),
]

for label, path, ref in FILES:
    print("=" * 74)
    print(label, ref)
    print("=" * 74)
    c = msmodel.Circuit.from_xml_file(path)
    ciid = c.find(ref)["ciid"]

    # 符号
    sym = None
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITSymbolComp" and inner[0].get("CiComponent") == ciid:
            sym = e
            break
    if sym is None:
        print("!! 无符号")
        continue

    # 全文 ID -> 元素索引（含所有 Item）
    idmap = {}
    for el in c.tree.iter("Item"):
        if el.get("ID"):
            idmap.setdefault(el.get("ID"), []).append(el)

    defs = []
    for cl in sym.iter("ConnectList"):
        for it in cl.findall("Item"):
            defs.append(it.get("ID"))

    print("符号 ID=%s 引脚定义 %d 个" % (sym.get("ID"), len(defs)))
    for did in defs:
        cands = idmap.get(did, [])
        print("\n  def %s : 出现 %d 次" % (did, len(cands)))
        for el in cands:
            n = len(list(el))
            tag = "自闭合引用" if n == 0 else "正式定义(%d 子项)" % n
            print("     %s  父=%s" % (tag, "?"))
            if n:
                print("     ", ET.tostring(el, encoding="unicode")[:700].replace("\n", " "))
    print()
