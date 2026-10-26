# -*- coding: utf-8 -*-
"""P18: 导出 RefDesMgr 整段（含 CSCH_CAPVirtualComponentPin），看引脚→网络缓存结构。

buck.ms14 有 27 条（正好等于元件引脚总数），我们生成的是 0 条。
SPICE 模板里的 %t<n> 极可能从这里取网络名。

用法: runtime\py32\python.exe tools\p18_refdes.py <ms14>
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = sys.argv[1]
c = msmodel.Circuit.load(SRC)


def pretty(el, maxlen=6000):
    xml = ET.tostring(el, encoding="unicode")
    try:
        import xml.dom.minidom as md
        xml = md.parseString(xml).toprettyxml(indent="  ")
    except Exception:
        pass
    return xml[:maxlen]


# 找 RefDesMgr 节点
found = None
for e in c.tree.iter():
    if "RefDesMgr" in (e.tag or "") or "RefDesMgr" in (e.get("Class") or ""):
        found = e
        break
if found is None:
    print("没有 RefDesMgr")
    sys.exit(0)

print("RefDesMgr tag=%s Class=%s 子节点=%s" % (found.tag, found.get("Class"),
                                              [x.tag for x in found]))
print(pretty(found, 8000))
