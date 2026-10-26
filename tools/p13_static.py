# -*- coding: utf-8 -*-
"""P13 静态：克隆电阻 vs donor 原电阻的端子映射全量对比。

看：
  CiComponent/Ports 顺序、每个 CiPort 的 LocalName/Component/Nodes
  CIITPinSymbolComp 的 PinName / PortID
  Attributes[3] / Attributes[5]（CiaCollString：家族、型号、SPICE 模板）
  该元件在 CiNode 里的成员关系
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild


def dump(c, refdes, label):
    comp = c.find(refdes)
    ciid = comp["ciid"]
    inner = comp["comp"]
    print("=" * 74)
    print("%s  位号=%s CiID=%s" % (label, refdes, ciid))
    print("  CiComponent 属性:", dict(inner.attrib))
    ports_el = inner.find("Ports")
    order = [i.get("CiID") for i in ports_el] if ports_el is not None else []
    pmap = {p["ciid"]: p for p in c.ports()}
    print("  Ports 列表顺序:", order)
    for pid in order:
        p = pmap.get(pid)
        if not p:
            print("     %s -> (不存在!)" % pid)
            continue
        nd = p["port"].find("Nodes")
        nodes = [i.get("CiID") for i in nd] if nd is not None else []
        print("     %-12s LocalName=%-8s Component=%s Nodes=%s"
              % (pid, p["port"].get("LocalName"), p["port"].get("Component"), nodes))
    # 节点名
    for n in c.nodes():
        if set(n["ports"]) & set(order):
            print("     属于节点 %s name=%r" % (n["ciid"], n["name"]))
    sym = c.symbol_of(ciid)
    print("  引脚符号:")
    for el in sym.iter("CIITPinSymbolComp"):
        conn = el.find(".//CIITPinConnectorComp")
        defs = [i.get("ID") for i in conn.findall(".//ConnectList/Item")] if conn is not None else []
        print("     PinName=%-8s PortID=%-12s ConnectList=%s"
              % (el.get("PinName"), el.get("PortID"), defs))
    at = list(inner.find("Attributes"))
    for idx in (3, 4, 5):
        if idx < len(at):
            s = ET.tostring(at[idx], encoding="unicode")
            print("  Attributes[%d]: %s" % (idx, s[:600].replace("\n", " ")))


# 1) 指挥方的分压器
c = msmodel.Circuit.load(os.path.join(ROOT, "out", "p13_divider.ms14"))
print("p13_divider 元件:", [(x["refdes"], x["part"]) for x in c.components()])
for ref in ("R1", "R2"):
    try:
        dump(c, ref, "p13_divider")
    except KeyError:
        print("没有 %s" % ref)

# 2) donor 原件
d = msbuild.load_donor(os.path.join(ROOT, "out", "donor_spice.ms14"))
dump(d, "R1", "donor_spice 原 R1")
