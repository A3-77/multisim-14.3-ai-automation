# -*- coding: utf-8 -*-
"""P12：检查 corpus 缓存文件本身能不能读（区分「API 克隆不了」和「donor 文件坏了」）。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

data = json.load(open(os.path.join(ROOT, "corpus", "samples_index.json"), encoding="utf-8"))
bad = []
for e in data:
    p = e["cache"]
    try:
        msmodel.Circuit.load(p)
    except Exception as ex:
        head = open(p, "rb").read(24)
        bad.append((os.path.basename(p), type(ex).__name__, head))

print("不可读缓存 %d / %d" % (len(bad), len(data)))
for n, t, h in bad:
    print("  %-52s %-12s head=%r" % (n, t, h))
