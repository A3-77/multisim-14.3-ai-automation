# -*- coding: utf-8 -*-
"""对比 GND def：donor / p10 / mine(两个GND)。"""
import os
import sys
import gzip

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import xml.etree.ElementTree as ET


def show(c, label, def_ids):
    rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
    for e in rc:
        if e.get("ID") in def_ids and len(list(e)):
            print("=== %s def %s ===" % (label, e.get("ID")))
            print(ET.tostring(e, encoding="unicode")[:900])
            print()


donor = msmodel.Circuit(gzip.open(os.path.join(
    ROOT, "corpus", "samples",
    "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz"),
    "rb").read())
# donor 的 GND def
for e in donor.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITSymbolComp":
        for cl in e.iter("ConnectList"):
            for it in cl.findall("Item"):
                if it.get("ID"):
                    show(donor, "donor", {it.get("ID")})
                    break
            break
    break

p10 = msmodel.Circuit.from_xml_file("out/_p10.xml")
show(p10, "p10", {"741397208", "741395888"})
mine = msmodel.Circuit.from_xml_file("out/_accept.xml")
show(mine, "mine", {"233431296", "233431328"})
