# -*- coding: utf-8 -*-
"""对比两个 DC_POWER donor：3D 元件样例里的 V1 vs 真实电路样例里的 V1。"""
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dcl
import msmodel


def dump(path, refdes, tag):
    c = msmodel.Circuit.load(path)
    print("=" * 78)
    print("%s   %s @ %s" % (tag, os.path.basename(path), refdes))
    print("=" * 78)
    comp = c.find(refdes)
    if comp is None:
        print("  找不到 %s" % refdes)
        return
    print("  component():", {k: v for k, v in comp.items() if k in
                             ("ciid", "refdes", "family", "part", "class")})
    # 直接看电气对象子树里的关键字
    raw, _ = dcl.read_ms14(path)
    xml = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    tree = ET.fromstring(xml)
    ciid = comp.get("ciid")
    for el in tree.iter():
        if el.get("CiID") == ciid:
            s = ET.tostring(el, encoding="unicode")
            print("  对象大小: %d 字节" % len(s))
            for kw in ("Model", "SPICE", "Value", "PART", "Family", "Name"):
                cnt = s.count(kw)
                if cnt:
                    print("    含 %-8s x%d" % (kw, cnt))
            print("  片段:", s[:600].replace("\n", " ")[:600])
            break


dump(os.path.join(ROOT, "corpus", "samples14", "01 3D元件仿真.ms14"), "V1",
     "A) 索引命中的 donor（3D 元件样例）")
dump(os.path.join(ROOT, "corpus", "samples14",
                  "Amplificador para resistencia de 1mOhm.ms14"), "V1",
     "B) 真实电路样例里的 DC 源")
