# -*- coding: utf-8 -*-
"""阶段1 调查：DC_POWER 模板 / SimState 分析配置 / 原生样例 ground truth。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dcl
import msbuild
import msmodel

print("=" * 78)
print("1) DC_POWER 是否有 donor 模板")
print("=" * 78)
for key in [("POWER_SOURCES", "DC_POWER"),
            ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE"),
            ("POWER_SOURCES", "GROUND")]:
    try:
        hit = msbuild.find_part(*key)
        print("  %-40s -> %s @ %s" % (str(key), os.path.basename(hit[0]), hit[1]))
    except Exception as e:
        print("  %-40s -> ERR %s" % (str(key), e))

print()
print("=" * 78)
print("2) 我们生成的 AC 电路：SimState 里声明的是哪种分析")
print("=" * 78)
raw, info = dcl.read_ms14(os.path.join(ROOT, "out", "ref", "rc_lowpass_ir.ms14"))
xml = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
i = xml.find("SimState")
print(xml[i - 80:i + 900])

print()
print("=" * 78)
print("3) 原生 DC 电路样例：SimState 对比")
print("=" * 78)
cands = []
for d in ("corpus/samples14",):
    p = os.path.join(ROOT, d)
    if os.path.isdir(p):
        cands += [os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".ms14")]
print("  候选 %d 个" % len(cands))
for f in cands[:6]:
    try:
        raw, _info = dcl.read_ms14(f)
        xml = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        j = xml.find("SimState")
        seg = xml[j:j + 400].replace("&#10;", "\n")
        has_dc = "DC" in seg or "OPERATING" in seg.upper()
        print("\n  --- %s  (DC in SimState: %s)" % (os.path.basename(f), has_dc))
        print("  " + seg[:300].replace("\n", "\n  "))
    except Exception as e:
        print("  %s -> ERR %s" % (os.path.basename(f), e))
