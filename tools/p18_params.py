# -*- coding: utf-8 -*-
"""P18: 导出每个元件的 CiaParamList 全貌（doubles / parameters / paramindicators / strings）。

SPICE 模板里 #1 指第 1 个参数。若 parameters 里存的是显示串（&ASC1k）而不是
数值（1000.），那生成的网表行就是 rR1 1 2 &ASC1k —— 非法，整行被丢弃。

用法: runtime\py32\python.exe tools\p18_params.py <ms14>
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

c = msmodel.Circuit.load(sys.argv[1])
for e in c.elements:
    if e.get("Class") != "CiComponent":
        continue
    inner = list(e)[0]
    ln = inner.get("LocalName") or ""
    ref = ln.replace("&ASC", "") if ln.startswith("&ASC") else ln
    pls = inner.findall(".//CiaParamList")
    print("=" * 58)
    print("%-4s CiID=%s  CiaParamList 数=%d" % (ref, e.get("CiID"), len(pls)))
    for pl in pls:
        for part in ("doubles", "strings", "parameters", "paramindicators"):
            node = pl.find(part)
            if node is None:
                print("    %-15s <无>" % part)
                continue
            vals = [i.get("Value") for i in node.findall("Item")]
            print("    %-15s %s" % (part, vals))
