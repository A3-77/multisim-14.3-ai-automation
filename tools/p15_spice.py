# -*- coding: utf-8 -*-
"""P15 静态检查：把元件的 SPICE 模板/参数/标识全部打出来。

重点看 Attributes[1]（CiaSpiceTmpltExprt）和 Attributes[5]（CiaCollString 模板），
如果克隆时模板写错（例如电容模板写成电阻、%t1/%t2 丢失），元件就会短路或开路。

用法：python tools/p15_spice.py out/p15_sf.ms14
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def load(p):
    try:
        return msmodel.Circuit.load(p)
    except Exception:
        return msmodel.Circuit.from_xml_file(p)


def show_slot(el, idx):
    """把一个属性槽里的所有字符串/数字都抽出来。"""
    out = []
    for node in el.iter():
        tag = node.tag
        if tag == "CiaCollString":
            vals = [(i.get("Value") or "").replace("&ASC", "")
                    for i in node.iter("Item")]
            vals = [v for v in vals if v.strip()]
            if vals:
                out.append(("CiaCollString", vals))
        elif tag == "CiaCString":
            out.append(("CiaCString", node.get("String")))
        elif tag == "Item" and node.get("Value") is not None:
            out.append(("Item", node.get("Value")))
    return out


def main():
    p = sys.argv[1]
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    c = load(p)
    print("==", os.path.basename(p))
    for comp in c.components():
        attrs = comp["comp"].find("Attributes")
        print("\n--- %s (%s / %s) 槽数=%d"
              % (comp["refdes"], comp["family"], comp["part"],
                 len(list(attrs)) if attrs is not None else 0))
        if attrs is None:
            continue
        for idx in (0, 1, 2, 3, 4, 5):
            if idx >= len(list(attrs)):
                continue
            info = show_slot(list(attrs)[idx], idx)
            if info:
                print("   [%d] %s" % (idx, info))
        # 参数
        print("   params: %s" % (c.params(comp["comp"])[:6],))


if __name__ == "__main__":
    main()
