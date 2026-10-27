# -*- coding: utf-8 -*-
"""对目标元件做 donor 提取实验：引脚名 / 参数 / SPICE 模板 / 图形对象。"""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
import msbuild
import msmodel

TARGETS = [
    ("DIODE", "1N4007G"),
    ("DIODE", "1N4001"),
    ("DIODE", "1N914"),
    ("BJT_NPN", "2N2222A"),
    ("BJT_NPN", "2N3904"),
    ("BJT_PNP", "2N3906"),
    ("OPAMP", "LM358AD"),
    ("OPAMP", "741"),
    ("MOS_ENH_N", "IRF840"),
    ("ZENER", "1N4734A"),
    ("LED", "LED_red"),
]

def spice_template(comp):
    attrs = comp.find("Attributes")
    if attrs is None or len(attrs) < 2:
        return None
    for k in attrs[1].iter():
        s = k.get("String")
        if s:
            return s.replace("&ASC", "")
    return None

for fam, part in TARGETS:
    hit = msbuild.find_part(fam, part)
    print("\n" + "=" * 74)
    print("%s / %s" % (fam, part))
    if not hit:
        print("  !! 没有 donor")
        continue
    path, refdes = hit
    print("  donor : %s  [%s]" % (os.path.basename(path), refdes))
    c = msbuild.load_donor(path)
    comp = None
    for d in c.components():
        if d["refdes"] == refdes:
            comp = d
            break
    if comp is None:
        print("  !! donor 里找不到位号")
        continue
    ciid = comp["ciid"]
    pins = c.pin_info(ciid)
    print("  引脚   : %d 个 -> %s" % (len(pins), ", ".join(sorted(pins))))
    for nm in sorted(pins):
        print("           %-8s xy=%s" % (nm, pins[nm]["xy"]))
    params = c.params(comp["comp"])
    print("  参数槽 : %d 个 -> %s" % (len(params), params[:8]))
    tmpl = spice_template(comp["comp"])
    print("  SPICE  : %s" % (tmpl[:150] if tmpl else "(无)"))
    # 图形对象
    sym = c.symbol_of(ciid)
    n_obj = 0
    if sym is not None:
        n_obj = len(list(sym.iter("Element"))) + len(list(sym.iter("CDataElement")))
    print("  图形   : symbol=%s, 绘图元素 %d 个" % ("有" if sym is not None else "无", n_obj))
