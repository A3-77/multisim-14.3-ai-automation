# -*- coding: utf-8 -*-
"""P17 runner: 打开电路，把所有探针都作为输出，跑瞬态，逐个报 min/max/首/末。

用法: runtime\py32\python.exe tools\p17_run.py <ms14> [seconds]
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
print("rlc:", end=" ")
for r in ("V1", "R1", "R2", "C1"):
    try:
        print("%s=%s" % (r, c.rlc(r)), end="  ")
    except Exception as e:
        print("%s=<%s>" % (r, type(e).__name__), end="  ")
print()

res = {}
if outs:
    try:
        c.transient(SECS, sample_rate=200000.0, outputs=outs)
    except Exception as e:
        print("transient 批量读取失败(%s)，逐个读" % type(e).__name__)
    for nm in outs:
        try:
            t, v = c.read(nm)
        except Exception as e:
            print("%-14s 读取失败: %s" % (nm, e))
            continue
        if not v:
            print("%-14s 空数组" % nm)
            continue
        lo, hi = min(v), max(v)
        print("%-14s n=%-5d first=%-12.6g last=%-12.6g min=%-12.6g max=%-12.6g"
              % (nm, len(v), v[0], v[-1], lo, hi))
        res[nm] = {"n": len(v), "first": v[0], "last": v[-1], "min": lo, "max": hi}

out_json = os.path.splitext(SRC)[0] + ".p17.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump({"src": SRC, "outputs": outs, "stats": res,
               "state": str(c.state)}, f, ensure_ascii=False, indent=2)
print("已写", out_json)
sys.stdout.flush()
os._exit(0)
