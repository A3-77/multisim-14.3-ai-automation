# -*- coding: utf-8 -*-
"""P17: 通用 ConnectList 分析 —— 每个 ConnectList 的「宿主类」与「指向类」。

结构实际是 Item/CODPinComp/ConnectList/Item，之前按 Item/ConnectList 找漏了。

用法: runtime\py32\python.exe tools\p17_connectmap.py <ms14> [<ms14> ...]
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def walk(e, parent=None):
    yield e, parent
    for ch in e:
        for x in walk(ch, e):
            yield x


for src in sys.argv[1:]:
    c = msmodel.Circuit.load(src)
    print("=" * 62)
    print(os.path.basename(src))

    # 每个 ID 的类
    idcls = {}
    for e, p in walk(c.tree):
        for k in ("ID", "CiID"):
            v = e.get(k)
            if v:
                idcls.setdefault(v, e.get("Class") or e.tag)

    stat = Counter()
    for e, p in walk(c.tree):
        if e.tag != "ConnectList":
            continue
        host = p
        while host is not None and not host.get("Class"):
            host = None
        # 用最近的有 Class 的祖先
        anc = None
        # 重新向上找：walk 里没有存祖先链，这里用父级 Class 兜底
        hostcls = (p.get("Class") if p is not None else None) or "?"
        kinds = tuple(sorted({i.get("Class") or "?" for i in e.findall("Item")}))
        stat[(hostcls, ",".join(kinds) or "<空>")] += 1
    print("  ConnectList 宿主 -> 指向类:")
    for (h, k), v in stat.most_common(10):
        print("    %-28s -> %-40s %d" % (h, k, v))
