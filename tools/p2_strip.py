# -*- coding: utf-8 -*-
"""P2：把 7812 剥成一个"干净但结构完整"的基底。

删除：9 个元件及其全部关联（CiComponent/CiPort/CiModel/CiNode、绘图符号、导线、
      引脚定义、节点文字、探针、CiCircuit 索引、RefDesMgr 用量、NetLabels）
保留：全部全局结构（Extensions、RefDesMgr 骨架、ViewState、CDesignNetContainer 容器、
      CircPrefs、Background、PCBLayers、CiCircuitXMLizeHelper 等）

输出 out/rev_base_stripped.xml
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SRC = os.path.join(ROOT, "out", "rev_base.xml")
DST = os.path.join(ROOT, "out", "rev_base_stripped.xml")

t = ET.parse(SRC).getroot()

# ---- 建 parent 索引 ----
parent = {}
for p in t.iter():
    for c in p:
        parent[c] = p


def detach(e):
    p = parent.get(e)
    if p is not None:
        p.remove(e)


def count(tag=None, cls=None):
    n = 0
    for e in t.iter():
        if tag and e.tag != tag:
            continue
        if cls and (e.get("Class") or "") != cls:
            continue
        n += 1
    return n


def report(label):
    print("  %-26s CiComponent=%-3d CiPort=%-3d CiNode=%-3d CiModel=%-3d "
          "CiProbeComp=%-2d Probe=%-2d Link=%-3d Sym=%-3d PinDef=%-3d NodeText=%d"
          % (label,
             count(cls="CiComponent"), count(cls="CiPort"), count(cls="CiNode"),
             count(cls="CiModel"), count(cls="CiProbeComp"),
             count(cls="CIITProbeComponent"), count(cls="CIITLinkComp"),
             count(cls="CIITSymbolComp"), count(cls="CODPinComp"),
             count(cls="CODNodeTextComp")))


print("删除前：")
report("before")

elements = t.find(".//Elements")
objects = t.find(".//Components/CODComposite/Objects")
refcomp = t.find(".//Components/CODComposite/ReferencedComponents")

# ---- 1. Elements：删元件/引脚/节点/模型/探针，保留 CiCircuit ----
keep = []
removed_ciids = set()
for e in list(elements):
    cls = e.get("Class")
    if cls == "CiCircuit":
        keep.append(e)
        continue
    if cls in ("CiComponent", "CiPort", "CiNode", "CiModel", "CiProbeComp"):
        removed_ciids.add(e.get("CiID"))
        detach(e)
    else:
        keep.append(e)
print("\n从 Elements 删除全部 CiComponent/CiPort/CiNode/CiModel/CiProbeComp")

# ---- 2. CiCircuit：清空四个索引列表 ----
for e in t.iter("CiCircuit"):
    for tag in ("Models", "Nodes", "Probes", "Components"):
        nd = e.find(tag)
        if nd is not None:
            for i in list(nd):
                nd.remove(i)
    print("CiCircuit 索引已清空")

# ---- 3. Objects：删符号/导线/探针/节点文字 ----
n_obj = 0
for e in list(objects):
    inner = list(e)
    cls = inner[0].get("Class") if inner else None
    if cls in ("CIITSymbolComp", "CIITLinkComp", "CIITProbeComponent", "CODNodeTextComp"):
        detach(e)
        n_obj += 1
print("从 Objects 删除 %d 个对象" % n_obj)

# ---- 4. ReferencedComponents：清空（所有引脚定义都属于被删元件/探针）----
n_rc = 0
if refcomp is not None:
    for e in list(refcomp):
        detach(e)
        n_rc += 1
print("从 ReferencedComponents 删除 %d 个引脚定义" % n_rc)

# ---- 5. 自闭合的探针引用（ID=96255360 散落在别处的 3 个）----
n_ref = 0
for e in list(t.iter("Item")):
    if e.get("Class") == "CIITProbeComponent" and len(list(e)) == 0:
        detach(e)
        n_ref += 1
print("删除散落的探针引用 %d 个" % n_ref)

# ---- 6. RefDesPrefixUsageMap：清空已用编号，保留前缀骨架 ----
# 注意：必须先 list() 物化，否则下面 SubElement 加回的同名包装元素会被 iter 反复发现
for e in list(t.iter("RefDesPrefixUsage")):
    if e.get("Class"):                      # 只处理带 Class 的前缀条目
        for child in list(e):
            e.remove(child)
        e.set("NextNumber", "1")
        ET.SubElement(e, "RefDesPrefixUsage")   # 空的包装容器
print("RefDesPrefixUsage 已重置")

# ---- 7. RefDesMgr/ComponentPins：清空 ----
n_cp = 0
for e in t.iter("ComponentPins"):
    for i in list(e):
        e.remove(i)
        n_cp += 1
print("ComponentPins 清空 %d 条" % n_cp)

# ---- 8. CDesignNetContainer/NetLabels：清空 ----
n_nl = 0
for e in t.iter("NetLabels"):
    for i in list(e):
        e.remove(i)
        n_nl += 1
print("NetLabels 清空 %d 条" % n_nl)

# ---- 9. TotalProbeTriggers：重置 ----
for e in t.iter():
    if (e.get("Class") or "").endswith("CTotalProbeTriggers"):
        e.set("NextProbeID", "1")
        for ts in list(e):
            e.remove(ts)
        ET.SubElement(e, "TriggerSet")
        print("TotalProbeTriggers 已重置")

# ---- 10. InstrumentsData：7812 遗留下的仿真仪器显示缓存 ----
# CSourceSymbolCollectNode 的 COMPHANDLE/DISPLAYDATA 指向已删探针，必须整段删除
# （Multisim 会自行重建）
n_inst = 0
for e in list(t.iter("InstrumentsData")):
    detach(e)
    n_inst += 1
print("InstrumentsData 删除 %d 段" % n_inst)

print("\n删除后：")
report("after")

# ---- 校验：还有没有指向已删 CiID 的悬空引用 ----
alive = set()
for e in t.iter():
    for a in ("CiID", "ID"):
        v = e.get(a)
        if v and v.isdigit():
            alive.add(v)

dangling = {}
for e in t.iter():
    for a in ("CiID", "ID", "Component", "Circuit", "Scope", "Model",
              "SymCompID", "CiProbeComp", "Node", "Connect1", "Connect2", "Data"):
        v = e.get(a)
        if v and v.isdigit() and v not in alive and v in removed_ciids:
            dangling.setdefault((e.tag, a), set()).add(v)
print("\n悬空引用（指向已删对象）：")
if not dangling:
    print("  无")
for (tag, a), vs in sorted(dangling.items()):
    print("  %s@%s -> %s" % (tag, a, sorted(vs)[:5]))

# ---- 写出 ----
xml = ET.tostring(t, encoding="ascii", xml_declaration=True)
open(DST, "wb").write(xml)
print("\n写出 %s（%d 字节）" % (DST, len(xml)))
