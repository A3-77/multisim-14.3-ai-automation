# -*- coding: utf-8 -*-
"""P14m: 导出波形细节，判断是充电还是放电、tau 多少
用法: runtime\py32\python.exe tools\p14_wave.py <ms14> <csv>
"""
import csv
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1]
OUT = sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)


def _try_rlc(circ, ref):
    try:
        return circ.rlc(ref)
    except Exception:
        return None


outs = list(c.probes())
print("outputs:", outs)
print("rlc:", {r: _try_rlc(c, r) for r in ("R1", "C1", "V1")})
nm = outs[0]
for o in outs:
    if "探针" in o:
        nm = o
        break
print("读取:", nm)
data = c.transient(SECS, sample_rate=200000.0, outputs=[nm])
t, v = data[nm]
print("n=%d" % len(v))
print("前 12 点:")
for i in range(min(12, len(v))):
    print("   t=%.3e  V=%.6g" % (t[i], v[i]))
print("中段:")
for i in range(len(v) // 2 - 3, min(len(v) // 2 + 3, len(v))):
    print("   t=%.3e  V=%.6g" % (t[i], v[i]))
print("末 6 点:")
for i in range(max(0, len(v) - 6), len(v)):
    print("   t=%.3e  V=%.6g" % (t[i], v[i]))

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["time_s", nm])
    for a, b in zip(t, v):
        w.writerow([a, b])
print("已写", OUT)

# tau 估计：V(t)=V0*exp(-t/tau) → 找 V 降到 36.8% 的时间
import math
v0 = v[0]
for i in range(1, len(v)):
    if v[i] <= v0 * math.exp(-1) and v0 > 0:
        print("tau≈%.3e s (第 %d 点)" % (t[i] - t[0], i))
        break
sys.stdout.flush()
os._exit(0)
