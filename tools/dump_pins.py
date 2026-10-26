# -*- coding: utf-8 -*-
"""查 V1 引脚名与 def 的对应关系（mine / donor / p10）。"""
import os
import sys
import gzip

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def dump(c, label, refdes):
    comp = None
    for x in c.components():
        if x["refdes"] == refdes:
            comp = x
            break
    if comp is None:
        print("%s: 找不到 %s" % (label, refdes))
        return
    item = c.symbol_of(comp["ciid"])
    print("=== %s %s (ciid=%s) ===" % (label, refdes, comp["ciid"]))
    for pin in item.iter("CIITPinSymbolComp"):
        conn = pin.find(".//CIITPinConnectorComp")
        name = pin.get("PinName")
        portid = pin.get("PortID")
        refs = [i.get("ID") for i in conn.findall(".//ConnectList/Item")] if conn is not None else []
        print("  PinName=%-4s PortID=%-12s defs=%s" % (name, portid, refs))
    # 电气侧端口
    for p in c.ports():
        if p["component"] == comp["ciid"]:
            print("  CiPort name=%s ciid=%s" % (p["name"], p["ciid"]))


donor = msmodel.Circuit(gzip.open(os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz"),
    "rb").read())
dump(donor, "donor", "V2")
dump(msmodel.Circuit.from_xml_file("out/_p10.xml"), "p10", "V2")
dump(msmodel.Circuit.from_xml_file("out/_accept.xml"), "mine", "V1")
