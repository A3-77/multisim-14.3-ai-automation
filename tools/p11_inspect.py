# -*- coding: utf-8 -*-
"""P11 前置勘察：p10 里 V2 的对象边界（元件/模型/引脚/符号/引脚定义/节点/导线）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

c = msmodel.Circuit.from_xml_file(os.path.join(ROOT, "out", "_p10.xml"))
print("components:", [(x["refdes"], x["part"], x["ciid"]) for x in c.components()])
print("position V2:", c.position(c.find("V2")["ciid"]))
print("pin_info V2:", {k: v["xy"] for k, v in c.pin_info(c.find("V2")["ciid"]).items()})
print()
print("nodes:")
port_name = {}
for p in c.ports():
    port_name[p["ciid"]] = p
for n in c.nodes():
    names = []
    for pid in n["ports"]:
        p = port_name.get(pid)
        if p:
            ref = "?"
            for comp in c.components():
                if comp["ciid"] == p["component"]:
                    ref = comp["refdes"]
            names.append("%s.%s" % (ref, p["name"]))
        else:
            names.append(pid)
    print("  node %-10s name=%-6s ports=%s" % (n["ciid"], n["name"], names))
print()
print("wires:")
for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        lnk = inner[0]
        pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
        print("  wire %s Node=%s Connect1=%s Connect2=%s pts=%s"
              % (e.get("ID"), lnk.get("Node"), lnk.get("Connect1"), lnk.get("Connect2"), pts))
print()
print("probe:")
for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITProbeExtComponent":
        di = inner[0]
        print("  ID=%s M20/M21=%s/%s" % (e.get("ID"), di.get("Transformer-M20"), di.get("Transformer-M21")))
print()
print("pin defs (ReferencedComponents):")
for k, v in sorted(c.pin_defs().items(), key=lambda kv: kv[0]):
    print("  %s -> %s" % (k, v))
