# -*- coding: utf-8 -*-
"""列出 mine 全部 8 个引脚 def：位置、属主、被哪些导线引用。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

c = msmodel.Circuit.from_xml_file("out/_accept.xml")
rc = c.diagram.find("Components/CODComposite/ReferencedComponents")

# def ID -> (Center, Class)
defs = {}
for e in rc:
    if e.get("ID") and len(list(e)):
        inner = list(e)[0]
        defs[e.get("ID")] = (inner.get("CenterX"), inner.get("CenterY"), inner.get("Class"))

# def ID -> (refdes, pinname)
owner = {}
ref2ciid = {comp["refdes"] + ("#%d" % i if False else ""): comp["ciid"]
            for i, comp in enumerate(c.components())}
for comp in c.components():
    item = c.symbol_of(comp["ciid"])
    if item is None:
        continue
    for pin in item.iter("CIITPinSymbolComp"):
        conn = pin.find(".//CIITPinConnectorComp")
        if conn is None:
            continue
        for it in conn.findall(".//ConnectList/Item"):
            if it.get("ID"):
                owner[it.get("ID")] = (comp["refdes"], pin.get("PinName"))

print("=== 正式 def ===")
for did, (cx, cy, cls) in sorted(defs.items(), key=lambda kv: int(kv[0])):
    print("  def %-12s (%s,%s) %-14s 属主=%s" % (did, cx, cy, cls, owner.get(did)))

print()
print("=== 导线引用 ===")
for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        lnk = inner[0]
        c1, c2 = lnk.get("Connect1"), lnk.get("Connect2")
        pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
        print("  wire %-12s Node=%-12s %s(%s) -- %s(%s)  pts=%s"
              % (e.get("ID"), lnk.get("Node"),
                 c1, defs.get(c1, ("?",))[0:2] if c1 in defs else "?",
                 c2, defs.get(c2, ("?",))[0:2] if c2 in defs else "?",
                 pts))

print()
print("=== CiNode 成员 ===")
for e in c.elements:
    if e.get("Class") == "CiNode":
        inner = list(e)[0]
        ports = [i.get("CiID") for i in inner.find("Ports").findall("Item")]
        names = []
        for pid in ports:
            for p in c.ports():
                if p["ciid"] == pid:
                    rd = [k for k, v in ref2ciid.items() if v == p["component"]]
                    names.append("%s.%s" % (rd[0] if rd else "?", p["name"]))
        print("  node %-12s name=%s ports=%s" % (e.get("CiID"), inner.get("LocalName"), names))

print()
print("=== CiPort -> Nodes 反向引用 ===")
for p in c.ports():
    nd = p["port"].find("Nodes")
    refs = [i.get("CiID") for i in nd.findall("Item")] if nd is not None else []
    rd = [k for k, v in ref2ciid.items() if v == p["component"]]
    print("  %s.%s (ciid=%s) -> nodes=%s" % (rd[0] if rd else "?", p["name"], p["ciid"], refs))
