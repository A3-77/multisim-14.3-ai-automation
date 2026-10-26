# -*- coding: utf-8 -*-
"""P14o: 解析 ComponentPins/CSCH_CAPVirtualComponentPin 与 CiPort 的对应关系"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

for label, path, ref in (("buck", "out/_p14_buck.xml", "R1"),
                         ("donor", "out/_p14_donor.xml", "R1")):
    p = os.path.join(ROOT, path)
    c = msmodel.Circuit.from_xml_file(p)
    print("=" * 74)
    print(label, ref)
    print("=" * 74)

    # 找 ComponentPins 容器
    cp = None
    for el in c.tree.iter("ComponentPins"):
        cp = el
        break
    if cp is None:
        print("无 ComponentPins")
        continue
    print("ComponentPins 子项 %d" % len(list(cp)))
    # 结构样例
    for i, item in enumerate(list(cp)[:2]):
        print("  Item[%d] 属性: %s" % (i, dict(item.attrib)))
        for ch in item:
            print("     子:", ch.tag, dict(ch.attrib) if ch.tag != "Items" else "(%d 项)" % len(list(ch)))
        s = ET.tostring(item, encoding="unicode")
        print("   全量:", s[:800].replace("\n", " "))
        print()

    # R1 的端口 CiID / InstanceID
    ciid = c.find(ref)["ciid"]
    item = c._item_of(ciid)
    inner = item.find("CiComponent")
    print("R1 CiComponent InstanceID=%s" % inner.get("InstanceID"))
    for it in inner.find("Ports").findall("Item"):
        pid = it.get("CiID")
        port = c._item_of(pid).find("CiPort")
        print("   port %s LocalName=%s InstanceID=%s 属性=%s" % (
            pid, port.get("LocalName"), port.get("InstanceID"),
            {k: v for k, v in port.attrib.items()}))
