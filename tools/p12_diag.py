# -*- coding: utf-8 -*-
"""P12 诊断：rc_lowpass 的 V1 参数/模型 vs acceptance（已知能跑 5V）的 V1。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

FILES = [("rc", os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14")),
         ("accept", os.path.join(ROOT, "out", "ref", "acceptance.ms14"))]

for label, path in FILES:
    c = msmodel.Circuit.load(path)
    print("=" * 72)
    print(label, path)
    comp = c.find("V1")
    inner = comp["comp"]
    at = list(inner.find("Attributes"))
    print("  ident:", c.ident(inner))
    print("  params:", c.params(inner)[:4])
    print("  slot41:", at[41].find("CiaCString").get("String") if len(at) > 41 else None)
    print("  slot42:", at[42].find("CiaCString").get("String") if len(at) > 42 else None)
    print("  slot1  (CiaSpiceTmpltExprt):", ET.tostring(at[1], encoding="unicode")[:200].replace("\n", " "))
    print("  slot2  (CiaParamList):", ET.tostring(at[2], encoding="unicode")[:260].replace("\n", " "))
    model = None
    for e in c.elements:
        if e.get("CiID") == inner.get("Model"):
            model = e
    if model is not None:
        mi = list(model)[0]
        print("  model:", mi.attrib)
        print("  model xml:", ET.tostring(model, encoding="unicode")[:400].replace("\n", " "))
    print("  节点:")
    port_name = {p["ciid"]: p for p in c.ports()}
    for n in c.nodes():
        names = []
        for pid in n["ports"]:
            p = port_name.get(pid)
            if p:
                ref = next((x["refdes"] for x in c.components() if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        print("    %-10s name=%-5r ports=%s" % (n["ciid"], n["name"], names))
    print("  位置:", [(x["refdes"], c.position(x["ciid"])) for x in c.components()])
