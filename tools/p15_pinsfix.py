# -*- coding: utf-8 -*-
"""P15 实验：给生成文件补 ComponentPins（引脚->网名映射）和 RefDesGUIDsForSave。

SPICE 模板 r%p %t1 %t2 #1 里：
  %p    -> CIRToInfoMap（位号）           ← 上一轮已补
  %t1/%t2 -> ComponentPins（引脚->网名）  ← 这一轮补

ComponentPins 的 GUID 实测等于元件的 InstanceID（见 tools/p15_pins.py 输出）。
生成文件里这一节是空的，克隆元件的 InstanceID 又是新 GUID，查不到就解析不出端子。

用法：
  python tools/p15_pinsfix.py out/p15_sf.ms14 out/p15_sf_pins.ms14
  python tools/p15_pinsfix.py out/p15_sf.ms14 out/p15_sf_pins_nolastnet.ms14 --no-lastnet
"""
import argparse
import os
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import msmodel  # noqa: E402

PIN_CLASS = "CSCH_CAPVirtualComponentPin"   # donor 里连 R/L/GND 都用这个类名


def guid_of(comp_inner):
    v = comp_inner.get("InstanceID") or ""
    return v.replace("&ASC", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--no-lastnet", action="store_true",
                    help="lastnet 一律留空（默认写真实网名）")
    ap.add_argument("--tree", default="&ASC/",
                    help="TreeInstanceProxy 的值")
    a = ap.parse_args()

    src = a.src if os.path.isabs(a.src) else os.path.join(ROOT, a.src)
    dst = a.dst if os.path.isabs(a.dst) else os.path.join(ROOT, a.dst)

    c = msmodel.Circuit.load(src)

    ext = None
    for e in c.tree.iter("Extension"):
        if e.get("Class") == "CMultisimExtension":
            ext = e
            break
    if ext is None:
        raise SystemExit("没有 CMultisimExtension")

    mgrs = ext.find("RefDesMgrs")
    if mgrs is None:
        mgrs = ET.SubElement(ext, "RefDesMgrs")
    mgr = mgrs.find("RefDesMgr")
    if mgr is None:
        mgr = ET.SubElement(mgrs, "RefDesMgr")
        mgr.set("Class", "CIITHierRefDesManager")

    # ---- ComponentPins ----
    pins = mgr.find("ComponentPins")
    if pins is None:
        pins = ET.Element("ComponentPins")
        mgr.insert(0, pins)
    for it in list(pins):
        pins.remove(it)
    holder = ET.SubElement(pins, "Item")
    holder.set("TreeInstanceProxy", a.tree)
    items = ET.SubElement(holder, "Items")

    # 引脚 -> 网名
    pin_net = {}
    pm = {p["ciid"]: p for p in c.ports()}
    for nd in c.nodes():
        for pid in nd["ports"]:
            pin_net[pid] = nd["name"]

    n_pin = 0
    for comp in c.components():
        g = guid_of(comp["comp"])
        if not g:
            print("  !! %s 没有 InstanceID" % comp["refdes"])
            continue
        plist = [p for p in c.ports() if p["component"] == comp["ciid"]]
        for p in plist:
            pe = ET.SubElement(items, PIN_CLASS)
            pe.set("Class", PIN_CLASS)
            pe.set("GUID", g)
            pe.set("PinName", "&ASC" + p["name"])
            net = "" if a.no_lastnet else pin_net.get(p["ciid"], "")
            pe.set("lastnet", "&ASC" + net if net else "")
            n_pin += 1
        print("  %-5s %-32s GUID=%s 引脚=%s"
              % (comp["refdes"], comp["part"], g, [p["name"] for p in plist]))

    # ---- RefDesGUIDsForSave ----
    propmgr = ext.find("CCompInstancePropManager")
    if propmgr is None:
        propmgr = ET.SubElement(ext, "CCompInstancePropManager")
        propmgr.set("Class", "CCompInstancePropManager")
    save = propmgr.find("RefDesGUIDsForSave")
    if save is None:
        save = ET.SubElement(propmgr, "RefDesGUIDsForSave")
    for it in list(save):
        save.remove(it)
    for comp in c.components():
        g = guid_of(comp["comp"])
        if not g:
            continue
        it = ET.SubElement(save, "Item")
        it.set("TreeInstancePath", "&ASC/")
        it.set("TreeInstanceGuidPath", a.tree)
        it.set("CiCompGUID", "&ASC" + g)
        it.set("InstanceGUID", "{%s}" % str(uuid.uuid4()).upper())
        it.set("Gateswap", "1.")
        it.set("Pinswap", "1.")
        it.set("ComponentSpaceing", "-1.")
        it.set("ComponentGroup", "")

    xml = ET.tostring(c.tree, encoding="ascii", xml_declaration=True)
    size, _ = dcl.write_ms14(dst, xml)
    print("\n补了 %d 条引脚、%d 条 RefDesGUID -> %s (%s 字节)"
          % (n_pin, len(save), dst, size))


if __name__ == "__main__":
    main()
