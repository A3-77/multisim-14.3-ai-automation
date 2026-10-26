# -*- coding: utf-8 -*-
"""P17: 对比 RefDesMgr/ComponentPins 里的引脚注册项（CSCH_CAPVirtualComponentPin）。

这些项带 PinName + lastnet，是 Multisim 把 SPICE 模板里的 %t<n> 解析成网络名的
依据之一。donor 有 20 条，我们生成的 0 条 —— 需要确认「0 条」到底影不影响。

用法: runtime\py32\python.exe tools\p17_cpins.py <ms14> [<ms14> ...]
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

for src in sys.argv[1:]:
    c = msmodel.Circuit.load(src)
    print("=" * 60)
    print(src)
    n = 0
    classes = {}
    for e in c.tree.iter("Item"):
        cls = e.get("Class") or ""
        if "ComponentPin" in cls or "RefDes" in cls:
            classes[cls] = classes.get(cls, 0) + 1
        if "ComponentPin" in cls:
            n += 1
    print("  引脚注册项数:", n, " 相关类:", classes)
    shown = 0
    for e in c.tree.iter("Item"):
        cls = e.get("Class") or ""
        if "ComponentPin" not in cls:
            continue
        d = list(e)
        attrs = d[0].attrib if d else {}
        print("   ", cls, {k: attrs[k] for k in list(attrs)[:8]})
        shown += 1
        if shown >= 6:
            break
    # 顺带看 RefDesMgr 的整体形状
    for e in c.tree.iter("Item"):
        if e.get("Class") == "CSCH_RefDesManager" or "RefDesMgr" in str(e.get("Class")):
            print("   RefDesMgr:", e.get("Class"), [x.tag for x in e][:10])
