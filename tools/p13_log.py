# -*- coding: utf-8 -*-
"""P13：在 Connect 之前设日志文件，抓仿真日志原文 + 网表。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p13_a3.ms14")
LOG = os.path.join(ROOT, "out", "p13_sim.log")

for p in (LOG,):
    if os.path.exists(p):
        os.remove(p)

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim(connect=False)
try:
    ms._app.LogFile = LOG
    print("LogFile 设置 ok ->", LOG)
except Exception as e:
    print("LogFile 设置失败:", repr(e))
ms.connect()
print("connected:", ms.connected)

c = ms.open(SRC)
print("outputs:", c.probes())
try:
    print("=== netlist ===")
    print(c.netlist(with_probes=True))
except Exception as e:
    print("netlist 失败", repr(e))

nm = list(c.probes())[0]
c.request_output(nm, 2e6, 2000, method=msc.Interp.Linear)
c.run(0.001)
for _ in range(20):
    got, _t = c.wait(300)
    time.sleep(0.1)
    if got:
        break
print("state:", c.state_name, "last_error:", repr(c.last_error))
try:
    arr, _ = c._c.GetOutputData(nm)
    v = list(arr[1])
    print("V n=%d first=%.6g last=%.6g" % (len(v), v[0], v[-1]))
except Exception as e:
    print("取数失败", repr(e))

time.sleep(1.5)
print()
print("=== 日志 ===")
if os.path.exists(LOG):
    txt = open(LOG, "r", encoding="utf-8", errors="replace").read()
    print(txt[-6000:] if txt else "(空)")
else:
    print("(没有日志文件)")
sys.stdout.flush()
os._exit(0)
