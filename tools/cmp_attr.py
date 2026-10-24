# -*- coding: utf-8 -*-
"""对比真实样例里的电阻与自建电路里的电阻，找出值显示的全部存放位置。"""
import glob
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dcl

ROOT = os.path.dirname(HERE)


def load_xml(path):
    if path.endswith(".xml"):
        return open(path, "rb").read()
    xml, _ = dcl.read_ms14(path)
    return xml


def dump_comp(comp, label):
    print("=" * 70)
    print(label, "LocalName=", comp.get("LocalName"), "CiID=", comp.get("CiID"))
    attrs = comp.find("Attributes")
    if attrs is None:
        print("  无 Attributes")
        return
    for i, it in enumerate(list(attrs)):
        cls = it.get("Class", "")
        if cls == "CiaCString":
            s = "String=%r" % it.get("String")
        elif cls == "CiaParamList":
            parts = []
            for tag in ("doubles", "strings", "parameters", "ints"):
                el = it.find(tag)
                if el is None:
                    continue
                vals = [x.get("Value") for x in el.findall("Item")]
                parts.append("%s=%r" % (tag, vals))
            s = " ".join(parts)
        elif cls == "CiaCollString":
            vals = [x.get("Value") for x in it.findall(".//Item")]
            s = "CollString=%r" % (vals,)
        elif cls == "CiaDOUBLE":
            s = "Double=%r" % it.get("Double")
        else:
            s = ET.tostring(it, encoding="unicode")[:120].replace("\n", " ")
        if not s.strip() or s in ("<Item /> ",):
            continue
        print("  [%02d] %-16s %s" % (i, cls, s))


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "acceptance.ms14")
    xml = load_xml(target)
    tree = ET.fromstring(xml)
    print("### 目标文件:", target)
    for comp in tree.iter("CiComponent"):
        ln = comp.get("LocalName") or ""
        if "R" in ln:
            dump_comp(comp, "TARGET")
            break

    print("\n\n### 真实样例里的 1k 电阻")
    shown = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "out", "samples", "*.ms14"))):
        try:
            x = load_xml(f)
            t = ET.fromstring(x)
        except Exception:
            continue
        for comp in t.iter("CiComponent"):
            body = ET.tostring(comp, encoding="unicode")
            if "UNI1k_uc103a9" not in body:
                continue
            print("\n--- 来源:", os.path.basename(f))
            dump_comp(comp, "SAMPLE")
            shown += 1
            break
        if shown >= 2:
            break
    print("\n共展示", shown, "个样例电阻")


main()
