# -*- coding: utf-8 -*-
"""扫描语料库里所有电位器，看 doubles 各位置的实际取值分布。"""
import os
import sys
import glob
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

files = glob.glob(os.path.join(ROOT, "corpus", "samples14", "*.ms14"))
seen = Counter()
rows = []
for f in files[:400]:
    try:
        c = msbuild.load_donor(f)
    except Exception:
        continue
    for d in c.components():
        if "POT" not in str(d.get("part", "")).upper() and \
                "POT" not in str(d.get("family", "")).upper():
            continue
        comp = None
        for el in c.elements:
            if el.get("CiID") == d["ciid"]:
                comp = el
                break
        if comp is None:
            continue
        pl = comp.find(".//CiaParamList")
        if pl is None:
            continue
        dbl = [it.get("Value") for it in pl.find("doubles")]
        hum = [it.get("Value") for it in pl.find("parameters")]
        rows.append((os.path.basename(f), d["refdes"], dbl, hum))
        for i, v in enumerate(dbl):
            seen[i] += 1

print("共 %d 个电位器" % len(rows))
for r in rows[:25]:
    print(r[0], r[1], r[2], r[3])
