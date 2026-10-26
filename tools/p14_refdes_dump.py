# -*- coding: utf-8 -*-
"""P14p: 看空白基底 / 自建文件的 RefDesMgrs 结构，确定 ComponentPins 挂载点"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def dump(label, path):
    root = ET.parse(path).getroot()
    print("=" * 72)
    print(label)
    print("=" * 72)
    found = False
    for el in root.iter("RefDesMgrs"):
        found = True
        print("RefDesMgrs 子项 %d" % len(list(el)))
        for ch in el:
            print("   ", ch.tag, dict(ch.attrib) if ch.attrib else "")
            for ch2 in ch:
                print("       ", ch2.tag, dict(ch2.attrib) if ch2.attrib else "",
                      "子项=%d" % len(list(ch2)))
                for ch3 in ch2:
                    print("           ", ch3.tag, "子项=%d" % len(list(ch3)))
                    for ch4 in list(ch3)[:2]:
                        print("               ", ch4.tag,
                              dict(ch4.attrib) if ch4.attrib else "",
                              "子项=%d" % len(list(ch4)))
    if not found:
        print("没有 RefDesMgrs")
    print()


dump("blank 基底", os.path.join(ROOT, "out", "ref", "blank_circuit.xml"))
dump("自建 acceptance", os.path.join(ROOT, "out", "_accept3.xml"))
dump("buck 原生", os.path.join(ROOT, "out", "_p14_buck.xml"))
