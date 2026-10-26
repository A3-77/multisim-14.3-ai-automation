# -*- coding: utf-8 -*-
"""P18: 验证 mssafe 无损往返 —— 属性值里的换行是否被保住。

对比：
  S  ET 原生往返（已实测 I(PR1)=0）
  T  mssafe 往返     （期望 I(PR1)=13.9977，8/8 输出）

用法: runtime\py32\python.exe tools\p18_safe.py
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import mssafe

SRC = os.path.join(ROOT, "corpus", "samples14",
                   "Amplificador para resistencia de 1mOhm.ms14")
xml, info = dcl.read_ms14(SRC)

ok, pos = mssafe.self_check(xml)
print("mssafe 往返与原文完全一致: %s%s"
      % (ok, "" if ok else "（首个差异 @%d）" % pos))
if not ok:
    print("  原: %r" % xml[max(0, pos - 60):pos + 80])
    out = mssafe.roundtrip(xml)
    print("  新: %r" % out[max(0, pos - 60):pos + 80])

# 统计换行
n_orig = xml.count(b"\n")
n_safe = mssafe.roundtrip(xml).count(b"\n")
n_et = ET.tostring(ET.fromstring(xml), encoding="ascii").count(b"\n")
print("换行数: 原 %d  mssafe %d  ET %d" % (n_orig, n_safe, n_et))

out_t = os.path.join(ROOT, "out", "p18_T_safe.ms14")
n, _ = dcl.write_ms14(out_t, mssafe.roundtrip(xml))
print("T 写出 %s (%d 字节)" % (out_t, n))
