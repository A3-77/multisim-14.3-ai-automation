# -*- coding: utf-8 -*-
"""P7：把 donor_spice 剪成只剩 V-R-GND 回路，验证「删元件」是否破坏仿真。

保留：V2(DC_POWER)、R1(RESISTOR_VIRTUAL)、以及分别与 V2.2 / R1.2 同节点的两个 GND
删除：其余 7 个元件（V1/C1/C2/L1/L2 + 2 个无关 GND）及其全部关联

**导线策略（关键修正）**：
donor 的导线图依赖 junction（结点）语义——导线端点可以是"结点定义"，
多个结点定义共享一个结点对象。剪枝后无法保证连通（实测：V2.2 从网表里消失，
因为连它的导线全被删了 → V2 网表卡损坏 → 仿真拒绝）。
改为：删掉 donor 全部导线/结点文字/网络标签，按 CiNode 成员关系
用 msbuild.wire() 重建引脚链（该模型在 p5 产出过正确网表）。

新增：connect(net3 <-> net2) 把 V2 和 R1 闭成一个回路（B1 已验证无罪）
赋值：V2 = 5V，R1 = 1kΩ
探针：不加

输出 out/p7_isolate.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import msmodel  # noqa: E402
import msbuild  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SRC = os.path.join(ROOT, "out", "_donor_spice.xml")
OUT = os.path.join(ROOT, "out", "p7_isolate.ms14")

c = msmodel.Circuit.from_xml_file(SRC)
t = c.tree

parent = {}
for p in t.iter():
    for ch in p:
        parent[ch] = p


def detach(e):
    p = parent.get(e)
    if p is not None:
        p.remove(e)


# 被删对象 ID 全集（含子树内所有带 ID 的元素），用于最后清理自闭合引用项
dead_ids = set()


def kill(e):
    """删除元素，并把其子树里所有 ID 记进 dead_ids。"""
    for sub in e.iter():
        for a in ("ID", "CiID"):
            v = sub.get(a)
            if v and v.isdigit():
                dead_ids.add(v)
    detach(e)


# ---------- 1. 确定保留集 ----------
ref2ciid = {comp["refdes"]: comp["ciid"] for comp in c.components()}
V2, R1 = ref2ciid["V2"], ref2ciid["R1"]

node_of_port = {}
for n in c.nodes():
    for pid in n["ports"]:
        node_of_port[pid] = n["ciid"]

v2_p2 = [p for p in c.ports() if p["component"] == V2 and p["name"] == "2"][0]["ciid"]
r1_p2 = [p for p in c.ports() if p["component"] == R1 and p["name"] == "2"][0]["ciid"]
v2_node, r1_node = node_of_port[v2_p2], node_of_port[r1_p2]

gnds = [comp["ciid"] for comp in c.components() if comp["part"] == "GROUND"]
gnd_a = gnd_c = None
for g in gnds:
    gpin = [p for p in c.ports() if p["component"] == g][0]["ciid"]
    if node_of_port.get(gpin) == v2_node:
        gnd_a = g
    if node_of_port.get(gpin) == r1_node:
        gnd_c = g
assert gnd_a and gnd_c, "没找到与 V2/R1 同节点的 GND"

keep = {V2, R1, gnd_a, gnd_c}
print("保留: V2=%s R1=%s GND(a)=%s GND(c)=%s" % (V2, R1, gnd_a, gnd_c))

# ---------- 2. 导线/结点文字/网络标签：全删（随后按 CiNode 重建） ----------
n_wire = n_nt = 0
for e in list(c.objects):
    inner = list(e)
    if not inner:
        continue
    cls = inner[0].get("Class")
    if cls == "CIITLinkComp":
        kill(e)
        n_wire += 1
    elif cls == "CODNodeTextComp":
        kill(e)
        n_nt += 1
print("删除全部导线 %d 根、结点文字 %d 个" % (n_wire, n_nt))

n_nl = 0
for e in t.iter("NetLabels"):
    for lbl in list(e):
        e.remove(lbl)
        n_nl += 1
print("删除全部网络标签 %d 个" % n_nl)

# ---------- 3. 符号：删非保留元件的，收集其引脚定义 ----------
dead_defs = set()
for e in list(c.objects):
    inner = list(e)
    if not inner or inner[0].get("Class") != "CIITSymbolComp":
        continue
    if inner[0].get("CiComponent") not in keep:
        for cl in e.iter("ConnectList"):
            for it in cl.findall("Item"):
                if it.get("ID"):
                    dead_defs.add(it.get("ID"))
        kill(e)
print("符号已删，涉及引脚定义 %d 个" % len(dead_defs))

# ---------- 4. ReferencedComponents：删死引脚定义 ----------
rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
n_rc = 0
if rc is not None:
    for e in list(rc):
        if e.get("ID") in dead_defs:
            detach(e)
            n_rc += 1
print("引脚定义删除 %d 个" % n_rc)

# ---------- 5. Elements：删非保留的 CiComponent/CiPort/CiModel ----------
removed_ciids = set()
elements = t.find(".//Elements")
for e in list(elements):
    cls = e.get("Class")
    if cls == "CiComponent":
        if e.get("CiID") not in keep:
            removed_ciids.add(e.get("CiID"))
            kill(e)
    elif cls == "CiPort":
        comp = e.find("CiPort").get("Component")
        if comp not in keep:
            removed_ciids.add(e.get("CiID"))
            kill(e)
    elif cls == "CiModel":
        users = {cc.find("CiComponent").get("Model")
                 for cc in elements
                 if cc.get("Class") == "CiComponent" and cc.find("CiComponent") is not None}
        if e.get("CiID") not in users:
            removed_ciids.add(e.get("CiID"))
            kill(e)
print("Elements 删除，涉及 CiID %d 个" % len(removed_ciids))

# ---------- 6. CiCircuit：重建索引 + 重建各节点 Ports ----------
for e in t.iter("CiCircuit"):
    for tag in ("Models", "Nodes", "Probes", "Components"):
        nd = e.find(tag)
        if nd is None:
            continue
        for i in list(nd):
            if i.get("CiID") in removed_ciids:
                nd.remove(i)
    for node_item in list(elements):
        if node_item.get("Class") != "CiNode":
            continue
        inner = node_item.find("CiNode")
        ports_el = inner.find("Ports")
        if ports_el is None:
            continue
        for i in list(ports_el):
            if i.get("CiID") in removed_ciids:
                ports_el.remove(i)
        if len(list(ports_el)) == 0:
            kill(node_item)
            nd = e.find("Nodes")
            if nd is not None:
                for i in list(nd):
                    if i.get("CiID") == node_item.get("CiID"):
                        nd.remove(i)

# ---------- 7. ComponentPins 清空（RefDes 缓存，安全） ----------
for e in t.iter("ComponentPins"):
    for i in list(e):
        e.remove(i)

# ---------- 8. RefDesPrefixUsage 重置 ----------
for e in list(t.iter("RefDesPrefixUsage")):
    if e.get("Class"):
        for child in list(e):
            e.remove(child)
        e.set("NextNumber", "1")

# ---------- 9. InstrumentsData：COMPHANDLE 悬空就删 ----------
alive = set()
for e in t.iter():
    for a in ("ID", "CiID"):
        v = e.get(a)
        if v and v.isdigit():
            alive.add(v)
n_inst = 0
for e in list(t.iter("InstrumentsData")):
    handles = {d.get("Data") for d in e.iter("CDataElement")
               if d.get("Data") and d.get("Data").isdigit()}
    if handles and not (handles & alive):
        detach(e)
        n_inst += 1
print("InstrumentsData 删除 %d 段" % n_inst)

# ---------- 10. 通用清理：全文扫杀指向已删对象的自闭合引用项 ----------
n_sc = 0
for e in list(t.iter("Item")):
    if len(list(e)) == 0 and e.get("ID") in dead_ids:
        detach(e)
        n_sc += 1
print("自闭合引用项清理 %d 个（dead_ids 共 %d）" % (n_sc, len(dead_ids)))

# ---------- 11. 赋值 V2=5V R1=1k ----------
c.set_value_by_refdes("V2", 5.0)
c.set_value_by_refdes("R1", 1000.0)

# ---------- 12. Assembler 就位；按 CiNode 重建导线链 ----------
a = msbuild.Assembler.__new__(msbuild.Assembler)
a.c = c
a.els = c.elements
a.objs = c.objects
a.refcomp = rc
a.circuit_item = c.circuit_item
a.circuit_inner = c.circuit_item.find("CiCircuit")
a.circuit_ciid = c.circuit_item.get("CiID")

port_map = {}
for e in c.elements:
    if e.get("Class") == "CiPort":
        pin = e.find("CiPort")
        port_map[e.get("CiID")] = (pin.get("Component"),
                                    (pin.get("LocalName") or "").replace("&ASC", ""))

n_chain = 0
for node_item in list(c.elements):
    if node_item.get("Class") != "CiNode":
        continue
    ports_el = node_item.find("CiNode/Ports")
    if ports_el is None:
        continue
    pins = [port_map[i.get("CiID")] for i in ports_el if i.get("CiID") in port_map]
    for i in range(len(pins) - 1):
        a.wire(node_item.get("CiID"), pins[i], pins[i + 1])
        n_chain += 1
print("按 CiNode 重建导线 %d 根" % n_chain)

# ---------- 13. connect(V2.1, R1.1) 闭合成 V-R-GND 回路 ----------
n = a.connect([(V2, "1"), (R1, "1")], name="1")
print("connect(V2.1, R1.1) -> 新节点 %s" % n)

# ---------- 14. 保存 ----------
xml = ET.tostring(t, encoding="ascii", xml_declaration=True)
open(os.path.join(ROOT, "out", "_p7_isolate.xml"), "wb").write(xml)
dcl.write_ms14(OUT, xml)
print("写出 %s（XML %d 字节）" % (OUT, len(xml)))

back = msmodel.Circuit.load(OUT)
print("回读:", back.summary())
