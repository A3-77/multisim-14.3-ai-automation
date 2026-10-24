# -*- coding: utf-8 -*-
"""检查引脚名与探针结构。"""
import glob
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

DONOR = os.path.join(ROOT, "out", "samples",
                     "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.ms14")
c = msmodel.Circuit.from_xml_file(DONOR)
for ref in ("V2", "R1"):
    comp = c.find(ref)
    ps = [p for p in c.ports() if p["component"] == comp["ciid"]]
    print(ref, "引脚:", [(p["name"], p["ciid"]) for p in ps])

print("\n=== 探针（在 schema67 样例里找） ===")
for p in glob.glob(os.path.join(ROOT, "out", "samples", "*.ms14")):
    head = open(p, "rb").read(400).decode("ascii", "replace")
    if 'Schema="67"' not in head:
        continue
    try:
        r = ET.parse(p).getroot()
    except Exception:
        continue
    probes = r.findall(".//CiProbeComp")
    if not probes:
        continue
    print("---", os.path.basename(p))
    for pr in probes:
        print("   CiProbeComp attrs:", pr.attrib)
        par = [x for x in r.iter() if any(c is pr for c in x)]
        print("   父节点 Class:", par[0].get("Class") if par else None,
              "CiID:", par[0].get("CiID") if par else None)
        txt = ET.tostring(par[0], encoding="unicode") if par else ""
        print("   片段:", txt[:700].replace("\n", " "))
    break
