# -*- coding: utf-8 -*-
"""P14b: 对比 CiPort/Nodes 链与 CiNode 对象，判断 SPICE 端子解析依赖什么"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def inspect(path, refdes, label):
    print("=" * 72)
    print("%s / %s" % (label, refdes))
    print("=" * 72)
    c = msmodel.Circuit.from_xml_file(path)

    # 所有 CiNode 的 CiID
    node_ids = {}
    for e in c.elements:
        if e.get("Class") == "CiNode":
            inner = e.find("CiNode")
            node_ids[e.get("CiID")] = inner.get("LocalName") if inner is not None else "?"
    print("CiNode CiID: %s" % node_ids)

    comp = c.find(refdes)
    ciid = comp["ciid"]
    item = c._item_of(ciid)
    inner = item.find("CiComponent")
    ports_el = inner.find("Ports")

    print("\n-- CiPort 完整 XML（归一化 ID 前的原样）--")
    for it in ports_el.findall("Item"):
        pid = it.get("CiID")
        p = c._item_of(pid)
        s = ET.tostring(p, encoding="unicode")
        print("  port %s:" % pid)
        print("   ", s[:700].replace("\n", " "))
        pin = p.find("CiPort")
        nd = pin.find("Nodes") if pin is not None else None
        if nd is not None:
            for x in nd.findall("Item"):
                nid = x.get("CiID")
                print("      Nodes.Item CiID=%s -> 是 CiNode? %s" % (nid, nid in node_ids))
        print()

    # CiCircuit 索引里端口怎么登记的
    for e in c.elements:
        if e.get("Class") == "CiCircuit":
            ci = list(e)[0]
            for tag in ("Components", "Nodes", "Ports", "ComponentPins"):
                ch = ci.find(tag)
                if ch is None:
                    print("CiCircuit/%s: 不存在" % tag)
                else:
                    print("CiCircuit/%s: %d 项" % (tag, len(list(ch))))
            break
    print()


inspect(os.path.join(ROOT, "out", "_p14_donor.xml"), "R1", "donor")
inspect(os.path.join(ROOT, "out", "_p14_mine.xml"), "R1", "mine")
