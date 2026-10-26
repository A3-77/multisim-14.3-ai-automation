# -*- coding: utf-8 -*-
"""P14r: 从分压器里彻底删除 C1，得到纯电阻 V1-R1-中点-R2-GND"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "out", "p14_divider.ms14")
OUT = os.path.join(ROOT, "out", "p14_div_r.ms14")

xml, _ = dcl.read_ms14(SRC)
p = os.path.join(ROOT, "out", "_p14_div_r.xml")
open(p, "wb").write(xml)
c = msmodel.Circuit.from_xml_file(p)

ciid = c.find("C1")["ciid"]
item = c._item_of(ciid)
inner = item.find("CiComponent")
ports = [x.get("CiID") for x in inner.find("Ports").findall("Item")]
sym_id = inner.get("SymCompID")
print("C1 CiID=%s ports=%s sym=%s" % (ciid, ports, sym_id))

parent = {ch: pa for pa in c.tree.iter() for ch in pa}

# 1) 收集符号里引脚定义 ID（用于找导线）
pin_defs = set()
sym = None
for e in c.objects:
    if e.get("ID") == sym_id:
        sym = e
        break
if sym is not None:
    for cl in sym.iter("ConnectList"):
        for it in cl.findall("Item"):
            if it.get("ID"):
                pin_defs.add(it.get("ID"))
print("C1 引脚定义:", pin_defs)

# 2) 删除引用这些引脚定义的导线
dead_wires = set()
for e in list(c.objects):
    inner2 = list(e)
    if not inner2 or inner2[0].get("Class") != "CIITLinkComp":
        continue
    l = inner2[0]
    if l.get("Connect1") in pin_defs or l.get("Connect2") in pin_defs:
        dead_wires.add(e.get("ID"))
        c.objects.remove(e)
print("删除导线:", dead_wires)

# 3) 删除符号对象
if sym is not None:
    c.objects.remove(sym)

# 4) 删除 CiComponent + 端口，并从节点里摘掉
c.elements.remove(item)
for pid in ports:
    pitem = c._item_of(pid)
    port = pitem.find("CiPort")
    # 从 CiNode/Ports 摘除
    for e in c.elements:
        if e.get("Class") == "CiNode":
            pel = e.find("CiNode/Ports")
            if pel is not None:
                for r in list(pel):
                    if r.get("CiID") == pid:
                        pel.remove(r)
    c.elements.remove(pitem)

# 5) CiCircuit/Components 摘除
for e in c.elements:
    if e.get("Class") == "CiCircuit":
        comps = e.find("CiCircuit/Components")
        if comps is not None:
            for r in list(comps):
                if r.get("CiID") == ciid:
                    comps.remove(r)

# 6) ReferencedComponents 里删掉 C1 的引脚定义 + 相关自闭合引用
rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
dead = set(pin_defs) | dead_wires
for e in list(rc):
    if e.get("ID") in dead:
        rc.remove(e)
# 引脚定义本体
for e in list(rc):
    if e.get("Class") == "CODPinComp" and len(list(e)) and e.get("ID") in pin_defs:
        rc.remove(e)

# 7) 探针位置保持在中点导线上
c.save(OUT)
print("写出", OUT, os.path.getsize(OUT))

back = msmodel.Circuit.load(OUT)
pm = {q["ciid"]: q for q in back.ports()}
for nd in back.nodes():
    names = []
    for pid in nd["ports"]:
        q = pm.get(pid)
        if q:
            ref = next((x["refdes"] for x in back.components() if x["ciid"] == q["component"]), "?")
            names.append("%s.%s" % (ref, q["name"]))
    print("  node %-10s ports=%s" % (nd["ciid"], names))
