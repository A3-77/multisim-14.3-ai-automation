# -*- coding: utf-8 -*-
"""检查生成的电位器测试文件：元件、引脚、探针是否都在。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

p = os.path.join(ROOT, "out", "hw1", "pot_i3_10.ms14")
print("exists:", os.path.exists(p), os.path.getsize(p) if os.path.exists(p) else 0)
c = msbuild.load_donor(p)
for d in c.components():
    print(d["refdes"], d["family"], d["part"],
          {k: v["xy"] for k, v in c.pin_info(d["ciid"]).items()})
print("probes:", c.probes() if hasattr(c, "probes") else "n/a")
