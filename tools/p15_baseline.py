# -*- coding: utf-8 -*-
"""P15 基线：在 donor 自己的文件里用**原装**元件搭 V2-R1-中点-C1-GND。

零克隆（除探针），只改接线。这是判定「克隆过程坏了」还是「别处坏了」的唯一干净办法：
  中点读到 5V  -> 原装 R1 导通，问题确实出在克隆
  中点仍 0V    -> 原装 R1 也不导通，问题在克隆之外（GND/探针/SPICE 侧）

用法：python tools/p15_baseline.py
产物：out/p15_baseline.ms14
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

BASE = os.path.join(ROOT, "out", "_donor_spice.xml")
OUT = os.path.join(ROOT, "out", "p15_baseline.ms14")


def detach(c, ciid, pin):
    """把某元件某引脚从所有 CiNode 里双向摘出来。"""
    p = next(x for x in c.ports() if x["component"] == ciid and x["name"] == pin)
    removed = []
    for e in c.elements:
        if e.get("Class") != "CiNode":
            continue
        pe = e.find("CiNode/Ports")
        if pe is None:
            continue
        for it in list(pe):
            if it.get("CiID") == p["ciid"]:
                pe.remove(it)
                removed.append(e.get("CiID"))
    nd = p["port"].find("Nodes")
    if nd is not None:
        for it in list(nd):
            nd.remove(it)
    return removed


def attach(c, ciid, pin, node_id):
    p = next(x for x in c.ports() if x["component"] == ciid and x["name"] == pin)
    nd = p["port"].find("Nodes")
    if nd is None:
        nd = ET.SubElement(p["port"], "Nodes")
    ET.SubElement(nd, "Item").set("CiID", node_id)
    for e in c.elements:
        if e.get("CiID") == node_id:
            ET.SubElement(e.find("CiNode/Ports"), "Item").set("CiID", p["ciid"])
            return
    raise KeyError(node_id)


def main():
    a = msbuild.Assembler(base_path=BASE)
    c = a.c
    print("基底元件（全部原装）:")
    for x in c.components():
        print("   %-5s %-32s %s" % (x["refdes"], x["part"], x["ciid"]))

    v2 = c.find("V2")["ciid"]
    r1 = c.find("R1")["ciid"]
    c1 = c.find("C1")["ciid"]
    print("\nV2 参数:", c.params(c.find("V2")["comp"])[:3])
    print("R1 参数:", c.params(c.find("R1")["comp"])[:3])
    print("C1 参数:", c.params(c.find("C1")["comp"])[:3])

    # 找地节点：V2.2 所在的那个 CiNode
    gnd_node = None
    v2p2 = next(p for p in c.ports() if p["component"] == v2 and p["name"] == "2")
    nd = v2p2["port"].find("Nodes")
    if nd is not None and len(nd):
        gnd_node = list(nd)[0].get("CiID")
    print("V2.2 所在地节点:", gnd_node)
    if gnd_node is None:
        raise RuntimeError("V2.2 没有节点，donor 结构异常")

    # 改值：C1 用 100nF，让 RC 时间常数落在毫秒窗口内
    c.set_value_by_refdes("C1", 1e-7)
    c.set_value_by_refdes("R1", 50.0)
    print("改后 C1=%s R1=%s" % (c.params(c.find("C1")["comp"])[:2],
                              c.params(c.find("R1")["comp"])[:2]))

    # 摘掉旧连接
    for ciid, pin in ((v2, "1"), (r1, "1"), (r1, "2"), (c1, "1"), (c1, "2")):
        rm = detach(c, ciid, pin)
        print("  摘 %s.%s 于节点 %s" % (
            next(x["refdes"] for x in c.components() if x["ciid"] == ciid), pin, rm))

    # 重新接线：V2.1 -- R1.1 ; R1.2 -- C1.1(中点) ; C1.2 -- GND
    n_in = a.connect([(v2, "1"), (r1, "1")], name="IN")
    n_mid = a.connect([(r1, "2"), (c1, "1")], name="MID")
    attach(c, c1, "2", gnd_node)
    a.wire(gnd_node, (c1, "2"), (v2, "2"))
    print("  新节点 IN=%s MID=%s ; C1.2 挂到地 %s" % (n_in, n_mid, gnd_node))

    # 探针放中点导线顶点（R1.2 与 C1.1 之间那条线的拐点）
    ri = c.pin_info(r1)
    ci = c.pin_info(c1)
    print("  R1 引脚:", {k: v["xy"] for k, v in ri.items()})
    print("  C1 引脚:", {k: v["xy"] for k, v in ci.items()})
    px, py = ci["1"]["xy"][0], ri["2"]["xy"][1]
    clone_probe_ext(a, PROBE_DONOR, px, py)
    print("  探针 @ (%g,%g)" % (px, py))

    n, _ = a.save(OUT)
    print("\n写出 %s (%d 字节)" % (OUT, n))

    back = msmodel.Circuit.load(OUT)
    pm = {p["ciid"]: p for p in back.ports()}
    print("回读拓扑:")
    for nd2 in back.nodes():
        names = []
        for pid in nd2["ports"]:
            p = pm.get(pid)
            if p:
                ref = next((x["refdes"] for x in back.components()
                            if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        if names:
            print("  node %-10s name=%-4r %s" % (nd2["ciid"], nd2["name"], names))


if __name__ == "__main__":
    main()
