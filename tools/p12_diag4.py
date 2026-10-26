# -*- coding: utf-8 -*-
"""P12 诊断5：跑双探针文件，分别打印 in / out 两个探针的波形统计。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p12_diag2probe.ms14")

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)
print("components:", c.components())
outs = list(c.probes())
print("outputs:", outs)
for ref in ("R1", "R2", "C1"):
    try:
        print("rlc %s = %s" % (ref, c.rlc(ref)))
    except Exception as e:
        print("rlc %s 读不到（%r）" % (ref, e))

SEC, NSAMP = 0.001, 2000
for nm in outs:
    c.request_output(nm, NSAMP / SEC, NSAMP, method=msc.Interp.Linear)
c.run(SEC)
for i in range(30):
    st = c.state_name
    got, _ = c.wait(300)
    time.sleep(0.12)
    print("  poll", i, st, got)
    if got:
        break
    if st == "stopped" and i > 2:
        break

for nm in outs:
    try:
        arr, _ = c._c.GetOutputData(nm)
        t, v = list(arr[0]), list(arr[1])
        print("%-12s n=%-5d first=%.6g last=%.6g min=%.6g max=%.6g"
              % (nm, len(v), v[0], v[-1], min(v), max(v)))
    except Exception as e:
        print("%-12s 取数失败 %r last_error=%r" % (nm, e, c.last_error))
sys.stdout.flush()
os._exit(0)
