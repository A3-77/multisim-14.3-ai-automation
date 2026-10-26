# -*- coding: utf-8 -*-
"""P1：把 7812.ms12 的老式探针克隆进 acceptance.ms14，绑到 net1(&ASC1)。

老式探针对象图（实测自 samples/7812.ms12）：

    绘图对象  Item[ID] / CIITProbeComponent
                NetName="&ASC4"                       ← 显式网络绑定（关键！）
                Transformer-M20/M21                  ← 位置
                CiProbeComp="<电气CiID>"              ← 回指
                ElectricalObject/ModifierInfo
                ConnectList/Item[ID, Class=CODPinComp] × 2   ← 引脚定义 ID
    引脚定义  Components/CODComposite/ReferencedComponents
                Item[ID] / CODPinComp@CenterX,CenterY        ← 绝对坐标
    电气对象  Item[CiID] / CiProbeComp
                LocalName="&ASCProbe2"
                SymCompID="<绘图ID>"
                InstanceID="&ASC{GUID}"              ← 注意有 &ASC 前缀
                Circuit="<CiCircuit CiID>"
                Attributes[5] = "&ASCProbe%d"
                <Ports />                            ← 空
    注册      CiCircuit/Probes/Item[CiID]

 Triggers（TotalProbeTriggers/InstProbeTriggers）是可选的，NumTriggers=0，先不加。
"""
import copy
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import msmodel  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SRC = os.path.join(ROOT, "out", "ref", "acceptance.ms14")
DONOR = os.path.join(ROOT, "samples", "7812.ms12")
OUT = os.path.join(ROOT, "out", "p1_with_probe.ms14")

NET_NAME = "1"          # 绑到 net1（V1+ / R1 上端）
# 位置必须精确落在 net1 导线的顶点上（实测：落在线段中间 COM 不注册 output）
# acceptance 的 net1 导线顶点：(346,300) [V1 pin1]、(513,300)、(513,296) [R1 pin1]
PROBE_X, PROBE_Y = 346.0, 300.0
PROBE_NAME = "Probe1"


def find_probe_objects(circuit):
    """在 donor 电路里找第一个老式探针，返回 (绘图Item, 电气Item, 引脚定义ID列表)。"""
    draw = elec = None
    for e in circuit.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeComponent":
            draw = e
            break
    for e in circuit.elements:
        if e.get("Class") == "CiProbeComp":
            elec = e
            break
    if draw is None or elec is None:
        raise RuntimeError("donor 里找不到老式探针（draw=%s elec=%s）" % (draw, elec))

    conn = draw.find(".//CIITProbeComponent/ConnectList")
    def_ids = [i.get("ID") for i in conn.findall("Item")] if conn is not None else []
    return draw, elec, def_ids


def main():
    donor = msmodel.Circuit.load(DONOR)
    c = msmodel.Circuit.load(SRC)

    draw, elec, def_ids = find_probe_objects(donor)
    d_inner = draw.find("CIITProbeComponent")
    e_inner = elec.find("CiProbeComp")
    old_draw_id = draw.get("ID")
    old_elec_ciid = elec.get("CiID")
    old_pos = (float(d_inner.get("Transformer-M20")), float(d_inner.get("Transformer-M21")))
    print("donor 探针：绘图ID=%s 电气CiID=%s 位置=%s NetName=%r LocalName=%r 引脚定义=%s"
          % (old_draw_id, old_elec_ciid, old_pos, d_inner.get("NetName"),
             e_inner.get("LocalName"), def_ids))

    # donor 的引脚定义（ReferencedComponents 里）
    donor_defs = {}
    rc = donor.diagram.find("Components/CODComposite/ReferencedComponents")
    if rc is not None:
        for it in rc:
            if it.get("ID") in def_ids:
                donor_defs[it.get("ID")] = it
    print("donor 引脚定义找到：%s" % sorted(donor_defs))

    # ---- 目标电路的容器 -------------------------------------------
    tgt_rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
    if tgt_rc is None:
        tgt_rc = ET.SubElement(c.diagram.find("Components/CODComposite"),
                               "ReferencedComponents")
    probes_node = c.circuit_inner = None
    circuit_inner = None
    for e in c.elements:
        if e.get("Class") == "CiCircuit":
            circuit_inner = e.find("CiCircuit")
            break
    if circuit_inner is None:
        raise RuntimeError("目标电路没有 CiCircuit")
    probes_node = circuit_inner.find("Probes")
    if probes_node is None:
        probes_node = ET.SubElement(circuit_inner, "Probes")

    dx = PROBE_X - old_pos[0]
    dy = PROBE_Y - old_pos[1]

    # ---- 1. 克隆引脚定义并平移 ------------------------------------
    new_def_map = {}
    for old_id in def_ids:
        src = donor_defs.get(old_id)
        if src is None:
            continue
        nd = copy.deepcopy(src)
        nid = c.new_id()
        nd.set("ID", nid)
        inner = list(nd)[0]
        inner.set("CenterX", "%g" % (float(inner.get("CenterX")) + dx))
        inner.set("CenterY", "%g" % (float(inner.get("CenterY")) + dy))
        tgt_rc.append(nd)
        new_def_map[old_id] = nid
    print("新引脚定义：%s" % new_def_map)

    # ---- 2. 克隆绘图对象 ------------------------------------------
    new_draw = copy.deepcopy(draw)
    new_draw_id = c.new_id()
    new_draw.set("ID", new_draw_id)
    nd_inner = new_draw.find("CIITProbeComponent")
    nd_inner.set("Transformer-M20", "%g" % PROBE_X)
    nd_inner.set("Transformer-M21", "%g" % PROBE_Y)
    nd_inner.set("NetName", "&ASC" + NET_NAME)          # ← 显式绑网络
    # ConnectList 指向新引脚定义
    for it in nd_inner.findall(".//ConnectList/Item"):
        old = it.get("ID")
        if old in new_def_map:
            it.set("ID", new_def_map[old])
    c.objects.append(new_draw)

    # ---- 3. 克隆电气对象 ------------------------------------------
    new_elec = copy.deepcopy(elec)
    new_ciid = c.new_id()
    new_elec.set("CiID", new_ciid)
    ne_inner = new_elec.find("CiProbeComp")
    ne_inner.set("SymCompID", new_draw_id)
    nd_inner.set("CiProbeComp", new_ciid)               # ← 回指也要换成新的
    ne_inner.set("Circuit", circuit_inner.get("CiID") or
                 [e.get("CiID") for e in c.elements if e.get("Class") == "CiCircuit"][0])
    ne_inner.set("InstanceID", "&ASC{%s}" % str(uuid.uuid4()).upper())
    ne_inner.set("LocalName", "&ASC" + PROBE_NAME)
    # Attributes[5] 的显示名模板
    at = ne_inner.find("Attributes")
    if at is not None and len(list(at)) > 5:
        for cs in at[5].iter("CiaCollString"):
            items = cs.find("strings")
            if items is not None and len(list(items)) > 4:
                list(items)[4].set("Value", "&ASC" + PROBE_NAME + "%d")
    c.elements.append(new_elec)

    # ---- 4. 注册到 CiCircuit/Probes --------------------------------
    it = ET.SubElement(probes_node, "Item")
    it.set("CiID", new_ciid)

    # ---- 4b. 克隆 TotalProbeTriggers（donor 有，之前漏了）----------
    # 结构：CIITDiagram/TotalProbeTriggers/TriggerSet/InstProbeTriggers/Triggers/ProbeTriggers
    src_tpt = None
    for e in donor.tree.iter():
        if (e.get("Class") or "").endswith("CTotalProbeTriggers"):
            src_tpt = e
            break
    if src_tpt is not None:
        tpt = copy.deepcopy(src_tpt)
        tpt.set("NextProbeID", "2")
        for e in tpt.iter():
            if (e.get("Class") or "").endswith("CProbeTriggers"):
                e.set("NumTriggers", "0")
            if e.tag == "InstProbeTriggers":
                e.set("ProbeID", "1")
                e.set("TreeInstance", "&ASC#1/%s:" % os.path.splitext(
                    os.path.basename(SRC))[0])
        c.diagram.append(tpt)
        print("已克隆 TotalProbeTriggers（NextProbeID=2, ProbeID=1）")
    else:
        print("！donor 里没找到 TotalProbeTriggers")

    # ---- 5. 保存 ---------------------------------------------------
    n, body = c.save(OUT)
    print("\n写出 %s（文件 %d 字节，压缩体 %d 字节）" % (OUT, n, body))

    # ---- 6. 自检：回读 ---------------------------------------------
    back = msmodel.Circuit.load(OUT)
    print("\n回读自检：")
    print("  元件   :", [(x["refdes"], x["family"]) for x in back.components()])
    print("  节点   :", [(x["name"], len(x["ports"])) for x in back.nodes()])
    print("  导线   :", len([e for e in back.objects
                            if list(e) and list(e)[0].get("Class") == "CIITLinkComp"]))
    for e in back.elements:
        if e.get("Class") == "CiProbeComp":
            print("  探针   : CiID=%s LocalName=%r SymCompID=%s Circuit=%s"
                  % (e.get("CiID"), e.find("CiProbeComp").get("LocalName"),
                     e.find("CiProbeComp").get("SymCompID"),
                     e.find("CiProbeComp").get("Circuit")))
    for e in back.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeComponent":
            print("  探针绘图: ID=%s NetName=%r M20/M21=%s/%s CiProbeComp=%s ConnectList=%s"
                  % (e.get("ID"), inner[0].get("NetName"),
                     inner[0].get("Transformer-M20"), inner[0].get("Transformer-M21"),
                     inner[0].get("CiProbeComp"),
                     [i.get("ID") for i in inner[0].findall(".//ConnectList/Item")]))
    # Probes 注册
    for e in back.elements:
        if e.get("Class") == "CiCircuit":
            pr = e.find("CiCircuit/Probes")
            print("  Probes :", [i.get("CiID") for i in pr] if pr is not None else None)
            break
    # 引脚定义是否都在
    rc2 = back.diagram.find("Components/CODComposite/ReferencedComponents")
    ids = {it.get("ID") for it in rc2}
    miss = [i for i in new_def_map.values() if i not in ids]
    print("  引脚定义齐备:", not miss, "缺失:", miss)


if __name__ == "__main__":
    main()
