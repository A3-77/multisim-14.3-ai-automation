# -*- coding: utf-8 -*-
"""P18: 稳健的瞬态读取 —— 在 stop() 之前读数据。

msc.transient() 会在读之前 stop()，部分电路 stop 后数据就读不出来了
（GetOutputData 报「未指定的错误」）。本脚本改成：run -> wait -> read -> stop。

用法: runtime\py32\python.exe tools\p18_run2.py <ms14> [seconds]
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1]
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)
outs = list(c.probes())
print("outputs:", outs)
if not outs:
    sys.stdout.flush()
    os._exit(0)

sr = 200000.0
n = int(max(1000, SECS * sr * 1.2))
for nm in outs:
    try:
        c.request_output(nm, sr, n, method=msc.Interp.Linear)
    except Exception as e:
        print("request %s 失败: %s" % (nm, e))

c.run(SECS, pause=False)
deadline = time.time() + 25.0
got = ()
while time.time() < deadline:
    try:
        got, timed_out = c.wait(500)
    except Exception as e:
        print("wait 失败: %s" % (e,))
        break
    if got:
        break
    if c.state == msc.SimState.Stopped:
        break
print("state=%s got=%s" % (c.state, got))
time.sleep(0.5)

res = {}
for nm in outs:
    try:
        t, v = c.read(nm)
    except Exception as e:
        print("%-12s 读取失败: %s" % (nm, e))
        continue
    if not v:
        print("%-12s 空" % nm)
        continue
    print("%-12s n=%-5d first=%-12.6g last=%-12.6g min=%-12.6g max=%-12.6g"
          % (nm, len(v), v[0], v[-1], min(v), max(v)))
    res[nm] = {"n": len(v), "first": v[0], "last": v[-1], "min": min(v), "max": max(v)}

try:
    c.stop()
except Exception:
    pass

j = os.path.splitext(SRC)[0] + ".p18.json"
with open(j, "w", encoding="utf-8") as f:
    json.dump({"src": SRC, "outputs": outs, "stats": res}, f,
              ensure_ascii=False, indent=2)
print("已写", j)
sys.stdout.flush()
os._exit(0)
