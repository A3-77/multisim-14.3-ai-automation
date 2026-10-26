# -*- coding: utf-8 -*-
"""P18: 验证 buck.ms14 里的虚拟电阻到底导不导通。

做法：只改 R1 的阻值（1Ω / 5Ω原值 / 1MΩ），跑同样的瞬态，比较 V(PR1)。
      若 V(PR1) 完全不变 → 该虚拟电阻在原生文件里也不参与仿真
      → 「克隆导致开路」这个前提是错的，虚拟 R/C 在语料文件里本来就是摆设。

用法: runtime\py32\python.exe tools\p18_buckval.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = os.path.join(ROOT, "corpus", "samples14", "buck.ms14")
for tag, val in (("r1", 5.0), ("rlo", 1.0), ("rhi", 1e6)):
    c = msmodel.Circuit.load(SRC)
    c.set_value_by_refdes("R1", val)
    out = os.path.join(ROOT, "out", "p18_buck_%s.ms14" % tag)
    n, _ = c.save(out)
    print("%s R1=%g -> %s (%d 字节)  rlc=%s"
          % (tag, val, os.path.basename(out), n, c.rlc("R1") if hasattr(c, "rlc") else "?"))
