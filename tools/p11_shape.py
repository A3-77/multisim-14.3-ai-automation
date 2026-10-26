# -*- coding: utf-8 -*-
"""P11 容器结构对比：p10（能跑）vs acceptance（不跑）。

打印两棵树在 depth<=3 的骨架（tag: 子节点数 / 字节数），以及 acceptance 的
导线顶点、探针位置、net1 拓扑。
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

FILES = [("p10", os.path.join(ROOT, "out", "_p10.xml")),
         ("accept", os.path.join(ROOT, "out", "_accept.xml"))]


def skeleton(e, depth, maxd, out, prefix=""):
    if depth > maxd:
        return
    tag = e.tag
    n = len(list(e))
    size = len(ET.tostring(e, encoding="unicode"))
    key = prefix + "/" + tag + ("@%s" % e.get("Class") if e.get("Class") else "")
    out.append((depth, key, n, size))
    for ch in e:
        skeleton(ch, depth + 1, maxd, out, key)


for label, path in FILES:
    print("=" * 78)
    print(label, path)
    print("=" * 78)
    c = msmodel.Circuit.from_xml_file(path)
    rows = []
    skeleton(c.tree, 0, 3, rows)
    for d, k, n, s in rows:
        print("  " * d + "%-52s n=%-5d bytes=%d" % (k[-52:], n, s))
    print()

print("=" * 78)
print("acceptance 的导线 / 探针 / 节点")
print("=" * 78)
c = msmodel.Circuit.from_xml_file(FILES[1][1])
for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        lnk = inner[0]
        pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
        print("  wire %s Node=%s pts=%s" % (e.get("ID"), lnk.get("Node"), pts))
    if inner and inner[0].get("Class") == "CIITProbeExtComponent":
        print("  probe %s M20/M21=%s/%s" % (e.get("ID"), inner[0].get("Transformer-M20"),
                                            inner[0].get("Transformer-M21")))
port_name = {p["ciid"]: p for p in c.ports()}
for n in c.nodes():
    names = []
    for pid in n["ports"]:
        p = port_name.get(pid)
        if p:
            ref = next((x["refdes"] for x in c.components() if x["ciid"] == p["component"]), "?")
            names.append("%s.%s" % (ref, p["name"]))
        else:
            names.append("?" + pid)
    print("  node %-10s name=%-4s ports=%s" % (n["ciid"], n["name"], names))
print("  pin_info V1:", {k: v["xy"] for k, v in c.pin_info(c.find("V1")["ciid"]).items()})
print("  pin_info R1:", {k: v["xy"] for k, v in c.pin_info(c.find("R1")["ciid"]).items()})
