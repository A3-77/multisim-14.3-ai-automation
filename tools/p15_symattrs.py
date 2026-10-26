# -*- coding: utf-8 -*-
"""直接对比两个元件的 CIITSymbolComp 顶层属性字典（不递归），找隐藏/可见性差异。

用法：python tools/p15_symattrs.py out/p15_div3r.ms14 R1 R2
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def main():
    p = sys.argv[1]
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    a_ref = sys.argv[2] if len(sys.argv) > 2 else "R1"
    b_ref = sys.argv[3] if len(sys.argv) > 3 else "R2"
    c = msmodel.Circuit.load(p)

    def sym(ref):
        ciid = c.find(ref)["ciid"]
        item = c.symbol_of(ciid)
        inner = list(item)[0] if item is not None else None
        return item, inner

    ia, sa = sym(a_ref)
    ib, sb = sym(b_ref)
    print("== %s vs %s" % (a_ref, b_ref))
    print("Item 属性:")
    da, db = dict(ia.attrib), dict(ib.attrib)
    for k in sorted(set(da) | set(db)):
        mark = "" if da.get(k) == db.get(k) else "   <<<"
        print("   %-22s %-30r %r%s" % (k, da.get(k), db.get(k), mark))

    print("\nCIITSymbolComp 属性:")
    da, db = dict(sa.attrib), dict(sb.attrib)
    for k in sorted(set(da) | set(db)):
        mark = "" if da.get(k) == db.get(k) else "   <<<"
        print("   %-22s %-30r %r%s" % (k, da.get(k), db.get(k), mark))

    print("\nObjects 子对象清单:")
    for label, s in ((a_ref, sa), (b_ref, sb)):
        objs = s.find("Objects")
        print("  %s: %d 个" % (label, len(objs) if objs is not None else 0))
        if objs is None:
            continue
        for i, o in enumerate(objs):
            inner = list(o)
            cls = inner[0].get("Class") if inner else "?"
            hid = inner[0].get("Hidden") if inner else None
            print("     [%d] %-32s Hidden=%s" % (i, cls, hid))


if __name__ == "__main__":
    main()
