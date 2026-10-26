# -*- coding: utf-8 -*-
"""P11：符号对象内部的 PortID 引用对比（p10 原 V2 vs p11_a 克隆 V2 vs p11_b 移植 V1）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

CASES = [("p10(原)", os.path.join(ROOT, "out", "_p10.xml"), "V2"),
         ("A(克隆)", os.path.join(ROOT, "out", "p11_a.ms14"), "V2"),
         ("B(移植)", os.path.join(ROOT, "out", "p11_b.ms14"), "V1"),
         ("accept(克隆)", os.path.join(ROOT, "out", "_accept.xml"), "V1")]

for label, path, ref in CASES:
    c = msmodel.Circuit.load(path) if path.endswith(".ms14") else msmodel.Circuit.from_xml_file(path)
    ciid = c.find(ref)["ciid"]
    ports = {p["name"]: p["ciid"] for p in c.ports() if p["component"] == ciid}
    sym = c.symbol_of(ciid)
    print("=" * 70)
    print("%s  元件 %s CiID=%s  端口=%s" % (label, ref, ciid, ports))
    for pin in sym.iter("CIITPinSymbolComp"):
        print("   pinSymbol name=%-4s PortID=%-12s M20/M21=%s/%s"
              % (pin.get("PinName"), pin.get("PortID"),
                 pin.get("Transformer-M20"), pin.get("Transformer-M21")))
        for conn in pin.iter("CIITPinConnectorComp"):
            print("       connector PortID=%s ConnectList=%s"
                  % (conn.get("PortID"),
                     [i.get("ID") for i in conn.findall(".//ConnectList/Item")]))
    # 整个符号子树里所有指向端口 CiID 的属性
    all_port_ids = set(ports.values())
    hits = []
    for el in sym.iter():
        for k, v in el.attrib.items():
            if v in all_port_ids:
                hits.append((el.tag, k, v))
    print("   符号内指向本元件端口 CiID 的属性:", hits)
