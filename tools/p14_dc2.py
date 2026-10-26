# -*- coding: utf-8 -*-
"""P14h: dc_op / ac 多路径探测
用法: runtime\py32\python.exe tools\p14_dc2.py <ms14>
"""
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1]
subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)
outs = list(c.probes())
print("outputs:", outs)
nm = outs[0] if outs else None

def show(tag, fn):
    try:
        r = fn()
        print("%-38s OK -> %s" % (tag, str(r)[:300]))
        return r
    except Exception as e:
        print("%-38s 失败 -> %r" % (tag, e))
        return None

# 1) 先注册输出请求，再 DC
show("request_output(2e6,2000)", lambda: c.request_output(nm, 2e6, 2000, method=msc.Interp.Linear))
show("DoDCOperatingPoint([nm])", lambda: c._c.DoDCOperatingPoint([nm]))
show("GetOutputData(nm) after DC", lambda: list(c._c.GetOutputData(nm)[1])[:3])
show("OutputReady", lambda: c._c.OutputReady)

# 2) 不注册直接 DC
show("ClearOutputRequest + DC", lambda: (c._c.ClearOutputRequest(), c._c.DoDCOperatingPoint([nm])))
show("GetOutputData again", lambda: list(c._c.GetOutputData(nm)[1])[:3])

# 3) 交互式仿真 + 等待
show("RunSimulation(0.001)", lambda: c._c.RunSimulation(0.001))
for i in range(6):
    time.sleep(0.15)
    print("   state=%s ready=%s" % (c.state_name, getattr(c._c, "OutputReady", "?")))
show("GetOutputData after run", lambda: list(c._c.GetOutputData(nm)[1])[:3])
show("LastErrorMessage", lambda: c._c.LastErrorMessage)

# 4) AC 单频
show("DoACSingleFrequency(1000)", lambda: c._c.DoACSingleFrequency(1000.0, [nm]))
show("GetOutputData after AC", lambda: list(c._c.GetOutputData(nm)[1])[:3])

sys.stdout.flush()
os._exit(0)
