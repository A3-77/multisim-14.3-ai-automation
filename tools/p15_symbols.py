# -*- coding: utf-8 -*-
"""检查每个元件的绘图对象是否真的存在于 Objects 里，以及它的位置/引脚坐标。

元件在 CiComponent 里存在、RLCValue 也能读到，但如果绘图对象缺失或坐标异常，
画布上就看不见它 —— Multisim 也不会把它当电路的一部分参与仿真。

用法：python tools/p15_symbols.py out/p15_div3r.ms14
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
    c = msmodel.Circuit.load(p)
    print("==", os.path.basename(p))
    print("Objects 总数:", len(c.objects))

    for comp in c.components():
        ciid = comp["ciid"]
        sym = c.symbol_of(ciid)
        pos = c.position(ciid)
        pins = c.pin_info(ciid)
        print("\n%-5s %-30s CiID=%s" % (comp["refdes"], comp["part"], ciid))
        print("   绘图对象: %s" % ("有" if sym is not None else "*** 缺失 ***"))
        if sym is not None:
            inner = list(sym)
            print("   对象ID=%s 类=%s" % (sym.get("ID"),
                                        inner[0].get("Class") if inner else "?"))
        print("   位置: %s" % (pos,))
        for name, info in pins.items():
            print("   引脚 %-4s xy=%-18s def_ids=%s PortID=%s"
                  % (name, info["xy"], info["def_ids"], info.get("port")))

    # 所有绘图对象的 CiComponent 归属，找孤儿
    print("\n[Objects 归属]")
    owned = {}
    for item in c.objects:
        inner = list(item)
        if not inner:
            continue
        cls = inner[0].get("Class")
        owner = inner[0].get("CiComponent")
        owned.setdefault(owner, []).append(cls)
    for owner, clss in owned.items():
        ref = next((x["refdes"] for x in c.components() if x["ciid"] == owner), None)
        print("   CiComponent=%-12s -> %-40s %s"
              % (owner, ",".join(sorted(set(clss))),
                 "(%s)" % ref if ref else "*** 孤儿 ***"))


if __name__ == "__main__":
    main()
