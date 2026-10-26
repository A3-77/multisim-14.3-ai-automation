# -*- coding: utf-8 -*-
"""对比 blank 基底 / p10 / acceptance 的 RefDesMgr 与引脚编号结构"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl


def load(path):
    if path.endswith(".ms14") or path.endswith(".ms12"):
        xml, _ = dcl.read_ms14(path)
        return ET.fromstring(xml)
    return ET.parse(path).getroot()


def inv(root):
    c = Counter()
    for el in root.iter():
        c[el.get("Class") or el.tag] += 1
    return c


FILES = [
    ("blank", os.path.join(ROOT, "out", "ref", "blank_circuit.xml")),
    ("p10", os.path.join(ROOT, "out", "p10_probe.ms14")),
    ("accept", os.path.join(ROOT, "out", "ref", "acceptance.ms14")),
]

roots = {}
for label, path in FILES:
    if not os.path.exists(path):
        print("缺失:", path)
        continue
    roots[label] = load(path)

KEYS = ["RefDesMgr", "CIITHierRefDesManager", "CIRToInfoMap", "PinNumbersCIR",
        "PinOrderCIR", "RefDesData", "SharedPins", "CNetPropertyHandler",
        "CSchDesignNetLabel", "CDesignNetContainer", "CiCircuit", "CCircuitGeneral",
        "Extension", "CMultisimExtension", "CODProjectExtension", "CircuitParamData"]

print("%-28s %8s %8s %8s" % ("结构", "blank", "p10", "accept"))
for k in KEYS:
    row = []
    for label, _ in FILES:
        r = roots.get(label)
        row.append(inv(r).get(k, 0) if r is not None else -1)
    print("%-28s %8d %8d %8d" % (k, row[0], row[1], row[2]))

print()
for label, _ in FILES:
    r = roots.get(label)
    if r is None:
        continue
    print("=== %s Extensions 子项 ===" % label)
    for i, exts in enumerate(r.iter("Extensions")):
        kids = [(c.tag, c.get("Class") or "") for c in exts]
        print("  [%d] %s" % (i, kids))
    print()
