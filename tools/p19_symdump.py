# -*- coding: utf-8 -*-
"""P19-5：dump 一个元件在绘图树里的全部对象，找出真正的定位锚点。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

hit = msbuild.find_part("RESISTOR", "RESISTOR_VIRTUAL")
path, ref = hit
c = msbuild.load_donor(path)
d = msbuild.Donor(c, ref)
print("donor:", path, ref, " ciid=", d.ciid)
print("position() ->", d.pos)
print()

print("=== 绘图树里引用该元件的对象 ===")
for e in c.objects:
    inner = list(e)
    if not inner:
        continue
    cls = inner[0].get("Class")
    hit_it = any(el.get("CiComponent") == d.ciid for el in e.iter())
    if not hit_it:
        continue
    print("  Item ID=%-10s class=%-22s M20=%-8s M21=%-8s"
          % (e.get("ID"), cls, inner[0].get("Transformer-M20"),
             inner[0].get("Transformer-M21")))

print()
print("=== symbol_of() 返回的对象 ===")
sym = d.sym_item
print("  ID=", sym.get("ID") if sym is not None else None)
if sym is not None:
    inner = list(sym)[0]
    print("  class=", inner.get("Class"))
    for k in ("Transformer-M00", "Transformer-M01", "Transformer-M10",
              "Transformer-M11", "Transformer-M20", "Transformer-M21"):
        print("   %-18s = %s" % (k, inner.get(k)))

print()
print("=== 该元件的电气对象属性 ===")
comp = d.comp_item.find("CiComponent")
for k, v in comp.attrib.items():
    print("   %-16s = %s" % (k, v))

print()
print("=== 全部 CIITSymbolComp 的 (CiComponent, M20, M21) ===")
for e in c.objects:
    inner = list(e)
    if not inner or inner[0].get("Class") != "CIITSymbolComp":
        continue
    print("   ID=%-10s CiComponent=%-12s M20=%-8s M21=%-8s"
          % (e.get("ID"), inner[0].get("CiComponent"),
             inner[0].get("Transformer-M20"), inner[0].get("Transformer-M21")))
