# -*- coding: utf-8 -*-
"""列出 .ms14 里所有元件引脚坐标 + 探针落点，用于排查探针没注册。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msmodel  # noqa: E402


def dump(path):
    c = msmodel.Circuit.load(path)
    print("=== %s" % os.path.basename(path))
    comps = {i["ciid"]: i["refdes"] for i in c.components()}
    pins = []
    for ciid, ref in comps.items():
        info = c.pin_info(ciid)
        for name, d in info.items():
            pins.append((ref, name, round(d["xy"][0], 2), round(d["xy"][1], 2)))
    for p in sorted(pins, key=lambda t: (t[0], t[1])):
        print("  pin %-6s %-6s (%8.2f, %8.2f)" % p)
    # 探针
    for e in c.elements:
        if e.get("Class") == "CiPort":
            nm = (e.find("CiPort").get("LocalName") or "")
            if "UNI" in nm:
                comp = comps.get(e.find("CiPort").get("Component"), "?")
                print("  probe %-28s comp=%s" % (nm, comp))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        dump(p)
