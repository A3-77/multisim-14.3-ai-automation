# -*- coding: utf-8 -*-
"""检查 .ms14 解压 XML 里的悬空引用。

收集所有"定义"（带 ID/CiID 属性的元素），再扫描所有"引用"属性，
报告指向不存在对象的引用。用于 Multisim 加载后静默丢弃对象的排查。

用法：python check_dangling.py <xml 路径> [更多路径...]
"""
import re
import sys
import xml.etree.ElementTree as ET

# 引用属性名 → 说明
REF_ATTRS = [
    "Connect1", "Connect2", "Node", "NodeText", "CiProbeComp", "SymCompID",
    "Circuit", "Scope", "CiID", "ID",
]


def check(path):
    tree = ET.parse(path)
    root = tree.getroot()

    defined = set()
    # 真正的"定义"：Item 带 ID/CiID 且含有与 Class 同名的子元素。
    # ConnectList/Links 里的引用项也带 ID，但没有子元素，不能算定义。
    for el in root.iter():
        cls = el.get("Class")
        has_body = cls is not None and el.find(cls) is not None
        if not has_body:
            continue
        for a in ("ID", "CiID"):
            v = el.get(a)
            if v and v.isdigit():
                defined.add(v)

    problems = []
    for el in root.iter():
        tag = el.tag
        for a in REF_ATTRS:
            v = el.get(a)
            if v and v.isdigit() and v not in defined:
                problems.append((tag, a, v, el))

    # CDataElement Data= 里的 ID（MapData/COMPHANDLE 之类）
    for el in root.iter("CDataElement"):
        v = el.get("Data")
        if v and v.isdigit() and v not in defined:
            problems.append(("CDataElement", "Data", v, el))

    # 过滤已知良性模式：调色板索引 / 路径索引 / Scope=0 / 小整数 Data
    benign_tags = {"ColorInfo", "PathElement", "ERC_CHK_OPTIONS"}
    real = []
    for tag, a, v, el in problems:
        if tag in benign_tags:
            continue
        if tag == "CDataElement" and int(v) < 1000:
            continue
        real.append((tag, a, v, el))
    problems = real

    print("=== %s ===" % path)
    print("定义的对象 ID 数: %d" % len(defined))
    if not problems:
        print("悬空引用: 无")
    else:
        print("悬空引用: %d 处" % len(problems))
        for tag, a, v, el in problems:
            # 找上下文：父链
            ctx = _context(root, el)
            # 如果是 CiComponent/Ports 的悬空，标出元件 RefDes
            owner = _owner_refdes(root, el)
            extra = "  属于元件: %s" % owner if owner else ""
            print("  [%s] %s=%s  上下文: %s%s" % (tag, a, v, ctx, extra))
    print()
    return problems


def _owner_refdes(root, el):
    """向上找 CiComponent，返回其 RefDes。"""
    parent_map = {c: p for p in root.iter() for c in p}
    cur = el
    for _ in range(8):
        p = parent_map.get(cur)
        if p is None:
            return None
        if p.get("Class") == "CiComponent":
            inner = p.find("CiComponent")
            if inner is not None:
                return inner.get("RefDes") or p.get("CiID")
        cur = p
    return None


def _context(root, target):
    """找 target 元素的类别上下文（向上找最近的 Class 属性）。"""
    parent_map = {c: p for p in root.iter() for c in p}
    chain = []
    el = target
    for _ in range(6):
        p = parent_map.get(el)
        if p is None:
            break
        cls = p.get("Class") or p.tag
        chain.append(cls)
        el = p
    return " < ".join(chain[:4])


if __name__ == "__main__":
    total = 0
    for p in sys.argv[1:]:
        total += len(check(p))
    sys.exit(1 if total else 0)
