# -*- coding: utf-8 -*-
"""对比 def 的 Center 坐标与引脚实际坐标（donor / mine）。"""
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
    print("=== %s %s ===" % (label, refdes))
    rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
    defs = {}
    for e in rc:
        if e.get("ID"):
            inner = list(e)
            if inner:
                defs[e.get("ID")] = (inner[0].get("CenterX"), inner[0].get("CenterY"))
    for pin in item.iter("CIITPinSymbolComp"):
        conn = pin.find(".//CIITPinConnectorComp")
        name = pin.get("PinName")
        refs = [i.get("ID") for i in conn.findall(".//ConnectList/Item")] if conn is not None else []
        info = c.pin_info(comp["ciid"]).get(name.replace("&ASC", ""))
        xy = info["xy"] if info else None
        print("  PinName=%-6s pin_xy=%s  defs=%s centers=%s"
              % (name, xy, refs, [defs.get(r) for r in refs]))


donor = msmodel.Circuit(gzip.open(os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz"),
    "rb").read())
dump(donor, "donor", "V2")
dump(donor, "donor", "R1")
dump(msmodel.Circuit.from_xml_file("out/_p10.xml"), "p10", "V2")
dump(msmodel.Circuit.from_xml_file("out/_p10.xml"), "p10", "R1")
dump(msmodel.Circuit.from_xml_file("out/_accept.xml"), "mine", "V1")
dump(msmodel.Circuit.from_xml_file("out/_accept.xml"), "mine", "R1")
