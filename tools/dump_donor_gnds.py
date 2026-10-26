# -*- coding: utf-8 -*-
"""列出 donor 全部 GND 的符号/连接器/def ID，确认可否取两个不同的 GND。"""
import os
import sys
import gzip

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

donor = msmodel.Circuit(gzip.open(os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz"),
    "rb").read())

print("=== donor GND 元件 ===")
for comp in donor.components():
    if comp["part"] == "GROUND":
        item = donor.symbol_of(comp["ciid"])
        conns = []
        defs = []
        for pin in item.iter("CIITPinSymbolComp"):
            conn = pin.find(".//CIITPinConnectorComp")
            if conn is not None:
                conns.append(conn.get("ID"))
                for it in conn.findall(".//ConnectList/Item"):
                    if it.get("ID"):
                        defs.append(it.get("ID"))
        print("  refdes=%s ciid=%s symbolItem=%s connectors=%s defs=%s"
              % (comp["refdes"], comp["ciid"], item.get("ID") if item is not None else None,
                 conns, defs))

print()
print("=== ReferencedComponents 里 CIITPinConnectorComp 条目 ===")
rc = donor.diagram.find("Components/CODComposite/ReferencedComponents")
for e in rc:
    if e.get("Class") == "CIITPinConnectorComp":
        print("  ID=%s 子元素数=%d" % (e.get("ID"), len(list(e))))
