# -*- coding: utf-8 -*-
"""P15 深挖：克隆件与原件逐节点/逐属性 diff（不只比 Attributes）。

P13 只比了 Attributes 的 47 个槽，全一致；说明差异在「引用」或「子节点」层面。
这里把 CiComponent / CiPort / 绘图对象 / CODPinComp 四类子树全部展开对比。

用法：python tools/p15_deepdiff.py out/p15_refdes_yes.ms14 R1 out/_donor_spice.xml R1
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def load(path):
    try:
        return msmodel.Circuit.load(path)
    except Exception:
        return msmodel.Circuit.from_xml_file(path)


def sig(el, drop_ids=True):
    """把子树拍平成 [(路径, 属性字典)]，可选去掉 ID 类属性。"""
    out = []

    def walk(e, path):
        attrs = dict(e.attrib)
        if drop_ids:
            for k in ("CiID", "ID", "InstanceID", "GUID", "SymCompID",
                      "Component", "PortID", "Circuit", "Scope", "CiProbeComp"):
                if k in attrs:
                    attrs[k] = "<id>"
        out.append((path, attrs))
        seen = {}
        for ch in e:
            n = seen.get(ch.tag, 0)
            seen[ch.tag] = n + 1
            walk(ch, "%s/%s[%d]" % (path, ch.tag, n))

    walk(el, el.tag)
    return out


def diff(tag, a, b):
    sa, sb = sig(a), sig(b)
    da = {p: v for p, v in sa}
    db = {p: v for p, v in sb}
    problems = []
    for p in da:
        if p not in db:
            problems.append(("只在原件", p, ""))
            continue
        for k in set(da[p]) | set(db[p]):
            va, vb = da[p].get(k), db[p].get(k)
            if va != vb:
                problems.append(("值不同", p, "%s: %r -> %r" % (k, va, vb)))
    for p in db:
        if p not in da:
            problems.append(("只在克隆件", p, ""))
    if problems:
        print("  [%s] %d 处差异" % (tag, len(problems)))
        for kind, p, detail in problems[:40]:
            print("     %-10s %s" % (kind, p))
            if detail:
                print("                %s" % detail)
    else:
        print("  [%s] 完全一致（%d 个节点）" % (tag, len(sa)))
    return problems


def comp_items(c, refdes):
    ci = c.find(refdes)["ciid"]
    item = c._item_of(ci)
    sym = c.symbol_of(ci)
    ports = [p["node"] for p in c.ports() if p["component"] == ci]
    model = None
    mci = item.find("CiComponent").get("Model")
    if mci:
        for e in c.elements:
            if e.get("CiID") == mci:
                model = e
    return ci, item, sym, ports, model


def main():
    pa, ra = sys.argv[1], sys.argv[2]
    pb, rb = sys.argv[3], sys.argv[4]
    ca, cb = load(pa), load(pb)
    ia = comp_items(ca, ra)
    ib = comp_items(cb, rb)
    print("原件   %s @ %s" % (ra, pa))
    print("克隆件 %s @ %s" % (rb, pb))
    print("  CiID %s vs %s" % (ia[0], ib[0]))
    print("  Model: %r vs %r" % (ia[4] is not None, ib[4] is not None))
    print("  端口数 %d vs %d" % (len(ia[3]), len(ib[3])))
    print()
    diff("CiComponent", ia[1], ib[1])
    if ia[4] is not None and ib[4] is not None:
        diff("CiModel", ia[4], ib[4])
    if ia[2] is not None and ib[2] is not None:
        diff("绘图对象", ia[2], ib[2])
    for i, (x, y) in enumerate(zip(ia[3], ib[3])):
        diff("CiPort[%d]" % i, x, y)
    print()
    # CiComponent 自身的全部属性（不去 ID）
    print("CiComponent 属性对照：")
    aa, bb = dict(ia[1].find("CiComponent").attrib), dict(ib[1].find("CiComponent").attrib)
    for k in sorted(set(aa) | set(bb)):
        mark = "" if aa.get(k) == bb.get(k) else "   <<<"
        print("   %-24s %-42r %r%s" % (k, aa.get(k), bb.get(k), mark))


if __name__ == "__main__":
    main()
