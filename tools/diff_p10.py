# -*- coding: utf-8 -*-
"""diff 我的 acceptance.ms14 与 p10_probe.ms14 的探针/网络相关结构。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import xml.etree.ElementTree as ET


def find_probe(c):
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeExtComponent":
            return e
    return None


def find_probe_elec(c):
    for e in c.elements:
        if e.get("Class") == "CiProbeExtComp":
            return e
    return None


def diff_attrs(a, b, label):
    ka = dict(a.attrib)
    kb = dict(b.attrib)
    print("--- %s ---" % label)
    for k in sorted(set(ka) | set(kb)):
        va, vb = ka.get(k), kb.get(k)
        if va != vb:
            print("  %-28s mine=%-28s p10=%s" % (k, va, vb))


def main():
    mine = msmodel.Circuit.from_xml_file("out/_accept.xml")
    p10 = msmodel.Circuit.from_xml_file("out/_p10.xml")

    pd, pe = find_probe(mine), find_probe_elec(mine)
    qd, qe = find_probe(p10), find_probe_elec(p10)

    diff_attrs(list(pd)[0], list(qd)[0], "绘图对象 CIITProbeExtComponent")
    diff_attrs(list(pe)[0], list(qe)[0], "电气对象 CiProbeExtComp")

    # DefaultInstrumentProperties 的 key 对比
    pm = {el.get("Key") for el in list(pd)[0].iter("Element")}
    qm = {el.get("Key") for el in list(qd)[0].iter("Element")}
    print("--- DefaultInstrumentProperties keys ---")
    print("  mine 独有:", sorted(pm - qm))
    print("  p10  独有:", sorted(qm - pm))
    print("  共同 %d 个" % len(pm & qm))

    # 共同 key 里 Data 不同的
    pd_map = {el.get("Key"): el for el in list(pd)[0].iter("Element")}
    qd_map = {el.get("Key"): el for el in list(qd)[0].iter("Element")}
    print("--- Data 不同的 key ---")
    for k in sorted(pm & qm):
        da = pd_map[k].find("CDataElement")
        db = qd_map[k].find("CDataElement")
        va = da.get("Data") if da is not None else None
        vb = db.get("Data") if db is not None else None
        if va != vb:
            print("  %-40s\n    mine=%s\n    p10 =%s" % (k, str(va)[:120], str(vb)[:120]))

    # 电气对象的 Attributes 槽位数
    pa = list(list(pe)[0].find("Attributes"))
    qa = list(list(qe)[0].find("Attributes"))
    print("--- 电气 Attributes 槽: mine=%d p10=%d ---" % (len(pa), len(qa)))
    for i in range(max(len(pa), len(qa))):
        sa = ET.tostring(pa[i], encoding="unicode") if i < len(pa) else "(无)"
        sb = ET.tostring(qa[i], encoding="unicode") if i < len(qa) else "(无)"
        if sa != sb:
            print("  槽%d 不同:\n    mine=%s\n    p10 =%s" % (i, sa[:200], sb[:200]))

    # 导线对比（net1）
    print("--- 导线 ---")
    for label, c in (("mine", mine), ("p10", p10)):
        for e in c.objects:
            inner = list(e)
            if inner and inner[0].get("Class") == "CIITLinkComp":
                lnk = inner[0]
                pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
                print("  %-5s wire %s Node=%s pts=%s Connect=%s/%s"
                      % (label, e.get("ID"), lnk.get("Node"), pts,
                         lnk.get("Connect1"), lnk.get("Connect2")))

    # CiCircuit 探针相关注册
    print("--- CiCircuit ---")
    for label, c in (("mine", mine), ("p10", p10)):
        for e in c.elements:
            if e.get("Class") == "CiCircuit":
                inner = list(e)[0]
                for ch in inner:
                    if ch.tag in ("ProbeExts", "Probes", "Nodes", "Components", "Models"):
                        print("  %-5s %-12s %s" % (label, ch.tag,
                                                  [i.get("CiID") for i in ch]))
                break

    # CiProbeExtComp 在 Elements 里的父容器位置对比（mine 是追加在末尾）
    print("--- Elements 末尾 3 个 ---")
    for label, c in (("mine", mine), ("p10", p10)):
        tail = list(c.elements)[-3:]
        print("  %-5s %s" % (label, [(e.get("CiID"), e.get("Class")) for e in tail]))


if __name__ == "__main__":
    main()
