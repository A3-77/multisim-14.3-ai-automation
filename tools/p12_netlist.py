# -*- coding: utf-8 -*-
"""P12 诊断3：打开 rc_lowpass，导出网表看拓扑到底连成什么样。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14")

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)
print("components:", c.components())
print("outputs:", c.probes())
try:
    txt = c.netlist(with_probes=True)
    print("=== netlist ===")
    print(txt)
except Exception as e:
    print("netlist 失败:", repr(e), "last_error:", c.last_error)
sys.stdout.flush()
os._exit(0)
