# -*- coding: utf-8 -*-
"""P12 诊断7：开日志跑一遍，抓 Multisim 仿真日志原文。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p12_diag2probe.ms14")
LOG = os.path.join(ROOT, "out", "p12_sim.log")

if os.path.exists(LOG):
    os.remove(LOG)

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
try:
    ms.set_log_file(LOG)
    print("log ->", LOG)
except Exception as e:
    print("set_log_file 失败:", repr(e))

c = ms.open(SRC)
outs = list(c.probes())
print("outputs:", outs)
SEC, NSAMP = 0.001, 2000
for nm in outs:
    c.request_output(nm, NSAMP / SEC, NSAMP, method=msc.Interp.Linear)
c.run(SEC)
for i in range(20):
    got, _ = c.wait(300)
    time.sleep(0.12)
    if got:
        break
print("state:", c.state_name, "last_error:", repr(c.last_error))
for nm in outs:
    try:
        arr, _ = c._c.GetOutputData(nm)
        v = list(arr[1])
        print("%-12s n=%d first=%.6g last=%.6g" % (nm, len(v), v[0], v[-1]))
    except Exception as e:
        print(nm, "取数失败", repr(e))

time.sleep(1.0)
print()
print("=== 日志 ===")
if os.path.exists(LOG):
    txt = open(LOG, "r", encoding="utf-8", errors="replace").read()
    print(txt[-4000:])
else:
    print("(没有日志文件)")
sys.stdout.flush()
os._exit(0)
