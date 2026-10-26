# -*- coding: utf-8 -*-
"""P14c: 对比 R1 的符号对象 + 引脚定义（CODPinComp）"""
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

IDRE = re.compile(r"\b\d{6,}\b")


def norm(s):
    s = IDRE.sub("#", s)
    return re.sub(r">\s+<", "><", s)


def dump(path, refdes, label):
    print("=" * 74)
    print("%s / %s" % (label, refdes))
    print("=" * 74)
    c = msmodel.Circuit.from_xml_file(path)
    ciid = c.find(refdes)["ciid"]

    # 符号对象
    sym = None
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITSymbolComp" and inner[0].get("CiComponent") == ciid:
            sym = e
            break
    if sym is None:
        print("!! 找不到符号对象")
        return
    inner = list(sym)[0]
    print("-- 符号对象 ID=%s --" % sym.get("ID"))
    print("   CiComponent=%s SymCompID=%s" % (inner.get("CiComponent"), inner.get("SymCompID")))
    print("   Transformer:", {k: inner.get(k) for k in inner.attrib if k.startswith("Transformer")})
    print("   其他属性:", {k: v for k, v in inner.attrib.items()
                        if k not in ("Class", "CiComponent", "SymCompID") and not k.startswith("Transformer")})

    # 引脚符号 PortID
    print("\n-- CIITPinSymbolComp --")
    for ps in sym.iter("CIITPinSymbolComp"):
        print("   PinName=%s PortID=%s Center=(%s,%s)" % (
            ps.get("PinName"), ps.get("PortID"), ps.get("CenterX"), ps.get("CenterY")))

    # 符号的 ConnectList -> 引脚定义 ID
    print("\n-- 符号 ConnectList --")
    defs = []
    for cl in sym.iter("ConnectList"):
        for it in cl.findall("Item"):
            defs.append((it.get("ID"), it.get("Class")))
            print("   def ID=%s Class=%s" % (it.get("ID"), it.get("Class")))

    # 引脚定义本体（在 Objects/ReferencedComponents 的 ID 空间里找）
    idmap = {}
    for el in c.tree.iter("Item"):
        if el.get("ID"):
            idmap.setdefault(el.get("ID"), el)
    print("\n-- 引脚定义本体 --")
    for did, _cls in defs:
        d = idmap.get(did)
        if d is None:
            print("   %s !! 定义不存在" % did)
            continue
        print("   def %s:" % did)
        print("     ", norm(ET.tostring(d, encoding="unicode"))[:600])
        # 找 PortID / CiPort 引用
        for el in d.iter():
            for a in ("PortID", "CiPort", "Port", "Component"):
                v = el.get(a)
                if v:
                    print("       %s@%s = %s" % (el.tag, a, v))
    print()


dump(os.path.join(ROOT, "out", "_p14_donor.xml"), "R1", "donor")
dump(os.path.join(ROOT, "out", "_p14_mine.xml"), "R1", "mine")
