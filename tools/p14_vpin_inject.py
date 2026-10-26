# -*- coding: utf-8 -*-
"""P14q: 给分压器注入 ComponentPins（虚拟元件引脚登记表），验证是否让电阻进 SPICE deck"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "out", "p14_divider.ms14")
DONOR = os.path.join(ROOT, "out", "donor_spice.ms14")
OUT = os.path.join(ROOT, "out", "p14_div_vpin.ms14")

xml, _ = dcl.read_ms14(SRC)
p = os.path.join(ROOT, "out", "_p14_div_vpin.xml")
open(p, "wb").write(xml)
c = msmodel.Circuit.from_xml_file(p)

# 取 donor 的 TreeInstanceProxy 作为模板
d_xml, _ = dcl.read_ms14(DONOR)
d_root = ET.fromstring(d_xml)
proxy = None
for el in d_root.iter("ComponentPins"):
    it = el.find("Item")
    if it is not None:
        proxy = it.get("TreeInstanceProxy")
        break
print("TreeInstanceProxy 模板:", proxy)

# 找 RefDesMgr
mgr = None
for el in c.tree.iter("RefDesMgr"):
    if el.get("Class") == "CIITHierRefDesManager":
        mgr = el
        break
print("RefDesMgr:", mgr is not None)

cp = mgr.find("ComponentPins")
if cp is None:
    cp = ET.SubElement(mgr, "ComponentPins")
item = ET.SubElement(cp, "Item")
if proxy:
    item.set("TreeInstanceProxy", proxy)
items = ET.SubElement(item, "Items")

n = 0
for comp in c.components():
    item_el = c._item_of(comp["ciid"])
    inner = item_el.find("CiComponent")
    inst = inner.get("InstanceID")
    for pit in inner.find("Ports").findall("Item"):
        port = c._item_of(pit.get("CiID")).find("CiPort")
        pname = port.get("LocalName")
        e = ET.SubElement(items, "CSCH_CAPVirtualComponentPin")
        e.set("Class", "CSCH_CAPVirtualComponentPin")
        e.set("GUID", inst)
        e.set("PinName", pname)
        e.set("lastnet", "")
        n += 1
        print("  登记 %-4s %-8s %s" % (comp["refdes"], pname, inst))
print("共登记 %d 条" % n)

c.save(OUT)
print("写出", OUT, os.path.getsize(OUT))
