# -*- coding: utf-8 -*-
"""dump RefDesMgr/ComponentPins 的完整内容，并和元件的 InstanceID 对上号。

这一节是「引脚 -> 网名」的映射缓存，SPICE 模板里的 %t1/%t2 很可能从这里解析。
如果它为空，模板展开时端子名取不到，整行元件就废掉（连通性表却照常正确）。

用法：python tools/p15_pins.py out/_donor_spice.xml
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


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "_donor_spice.xml")
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    c = load(p)
    print("==", os.path.basename(p))

    ext = None
    for e in c.tree.iter("Extension"):
        if e.get("Class") == "CMultisimExtension":
            ext = e
            break
    if ext is None:
        print("没有 CMultisimExtension")
        return

    pins = ext.find("RefDesMgrs/RefDesMgr/ComponentPins")
    print("\n[ComponentPins]")
    if pins is None:
        print("  节点不存在")
    else:
        items = pins.findall("Item")
        print("  Item 数: %d" % len(items))
        for it in items:
            print("  TreeInstanceProxy: %s" % it.get("TreeInstanceProxy"))
            inner = it.find("Items")
            if inner is None:
                continue
            print("  引脚条目 %d 条:" % len(inner))
            for pe in inner:
                print("     %-34s GUID=%-40s PinName=%-6s lastnet=%r"
                      % (pe.tag, pe.get("GUID"), pe.get("PinName"), pe.get("lastnet")))

    # 元件 InstanceID 对照
    print("\n[元件 InstanceID]")
    for comp in c.components():
        inner = comp["comp"]
        print("   %-5s %-32s InstanceID=%s"
              % (comp["refdes"], comp["part"], inner.get("InstanceID")))

    # RefDesGUIDsForSave
    print("\n[RefDesGUIDsForSave]")
    mgr = ext.find("CCompInstancePropManager")
    if mgr is None:
        print("  CCompInstancePropManager 不存在")
    else:
        save = mgr.find("RefDesGUIDsForSave")
        if save is None:
            print("  节点不存在")
        else:
            print("  Item 数: %d" % len(save.findall("Item")))
            for it in save.findall("Item")[:20]:
                print("     CiCompGUID=%-44s InstanceGUID=%-40s"
                      % (it.get("CiCompGUID"), it.get("InstanceGUID")))


if __name__ == "__main__":
    main()
