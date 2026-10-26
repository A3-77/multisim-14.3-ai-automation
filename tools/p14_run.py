# -*- coding: utf-8 -*-
"""P14 通用运行器：打开 → probes → netlist → transient → 读数 → 抓仿真日志
用法: runtime\py32\python.exe tools\p14_run.py <ms14> <json> [seconds]
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
OUTJ = sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
LOG = os.path.join(ROOT, "out", "p14_sim.log")

if os.path.exists(LOG):
    os.remove(LOG)
subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

res = {"file": SRC, "outputs": [], "netlist": "", "v": {}, "state_seq": [],
       "last_error": "", "log_tail": "", "errors": []}

ms = msc.Multisim(connect=False)
try:
    ms._app.LogFile = LOG
except Exception as e:
    res["errors"].append("LogFile: %r" % (e,))
ms.connect()

c = ms.open(SRC)
try:
    res["outputs"] = list(c.probes())
    print("outputs:", res["outputs"])
except Exception as e:
    res["errors"].append("probes: %r" % (e,))

try:
    res["netlist"] = c.netlist(with_probes=True)
    print("=== netlist ===")
    print(res["netlist"])
except Exception as e:
    res["errors"].append("netlist: %r" % (e,))

if res["outputs"]:
    nm = res["outputs"][0]
    try:
        c.request_output(nm, 2e6, 2000, method=msc.Interp.Linear)
        c.run(SECS)
        seq = []
        for _ in range(25):
            seq.append(c.state_name)
            got, _t = c.wait(250)
            time.sleep(0.08)
            if got:
                break
        res["state_seq"] = seq
        arr, _ = c._c.GetOutputData(nm)
        v = list(arr[1])
        res["v"] = {"n": len(v), "first": v[0], "last": v[-1],
                    "min": min(v), "max": max(v)}
        print("V n=%d first=%.6g last=%.6g min=%.6g max=%.6g" % (
            len(v), v[0], v[-1], min(v), max(v)))
    except Exception as e:
        res["errors"].append("transient: %r" % (e,))
        print("取数失败", repr(e))

try:
    res["last_error"] = c.last_error or ""
except Exception:
    pass

time.sleep(1.5)
try:
    if os.path.exists(LOG):
        txt = open(LOG, "r", encoding="utf-8", errors="replace").read()
        res["log_tail"] = txt[-4000:]
        print("\n=== 日志尾部 ===")
        print(res["log_tail"][-2000:] if txt else "(空)")
except Exception as e:
    print("日志读取跳过:", repr(e))

json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.stdout.flush()
os._exit(0)
