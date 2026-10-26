# -*- coding: utf-8 -*-
"""P19-2：列出 acceptance_divider.ms14 的网络与导线顶点，给第二个探针选落点。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402

F = os.path.join(ROOT, "out", "ref", "acceptance_divider.ms14")
c = msmodel.Circuit.load(F)

print("=== 网络 ===")
for nd in c.nodes():
    print("  CiID=%-12s name=%-6s ports=%d" % (nd["ciid"], nd.get("name"), len(nd["ports"])))

print()
print("=== 导线（CIITLinkComp）===")
for e in c.objects:
    inner = list(e)
    if not inner:
        continue
    if inner[0].get("Class") != "CIITLinkComp":
        continue
    pts_el = inner[0].find("Points")
    pts = [(float(p.get("X")), float(p.get("Y"))) for p in pts_el] if pts_el is not None else []
    print("  ID=%-10s Node=%-12s pts=%s" % (e.get("ID"), inner[0].get("Node"), pts))

print()
print("=== 探针 ===")
for e in c.elements:
    if e.get("Class") == "CiProbeExtComp":
        i = e.find("CiProbeExtComp")
        print("  CiID=%s LocalName=%s InstanceID=%s"
              % (e.get("CiID"), i.get("LocalName"), i.get("InstanceID")))
for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITProbeExtComponent":
        print("  draw ID=%s M20=%s M21=%s"
              % (e.get("ID"), inner[0].get("Transformer-M20"), inner[0].get("Transformer-M21")))
