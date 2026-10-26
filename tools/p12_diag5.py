# -*- coding: utf-8 -*-
"""P12 诊断6：acceptance 的 R1（能导通）vs rc_lowpass 的 R1（开路）逐槽对比。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = [("accept-R1", os.path.join(ROOT, "out", "ref", "acceptance.ms14"), "R1"),
       ("rc-R1", os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14"), "R1"),
       ("rc-C1", os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14"), "C1")]

data = {}
for label, path, ref in SRC:
    c = msmodel.Circuit.load(path)
    comp = c.find(ref)
    inner = comp["comp"]
    at = list(inner.find("Attributes"))
    data[label] = {
        "attrib": dict(inner.attrib),
        "slots": [ET.tostring(x, encoding="unicode") for x in at],
        "n": len(at),
        "params": c.params(inner)[:6],
    }

a, b = data["accept-R1"], data["rc-R1"]
print("CiComponent 属性差异:")
for k in sorted(set(a["attrib"]) | set(b["attrib"])):
    va, vb = a["attrib"].get(k), b["attrib"].get(k)
    if va != vb:
        print("  %-16s accept=%-24r rc=%r" % (k, va, vb))
print()
print("槽数: accept=%d rc=%d" % (a["n"], b["n"]))
print("params: accept=%s rc=%s" % (a["params"], b["params"]))
print()
for i in range(max(a["n"], b["n"])):
    sa = a["slots"][i] if i < a["n"] else "(无)"
    sb = b["slots"][i] if i < b["n"] else "(无)"
    if sa != sb:
        print("--- 槽 %d ---" % i)
        print("  accept: %s" % sa[:420].replace("\n", " "))
        print("  rc    : %s" % sb[:420].replace("\n", " "))
