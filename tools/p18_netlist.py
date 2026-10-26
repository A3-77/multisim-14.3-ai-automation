# -*- coding: utf-8 -*-
"""P18: 调 ReportNetlist，看 Multisim 自己怎么分配节点。

用法: runtime\py32\python.exe tools\p18_netlist.py <ms14>
"""
import os
import subprocess
import sys
import time

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
print("outputs:", c.probes())

for probes in (False, True):
    for fmt in (0, 1):
        try:
            txt = c.netlist(with_probes=probes, fmt=fmt)
        except Exception as e:
            print("probes=%s fmt=%d 失败: %s" % (probes, fmt, e))
            continue
        print("=" * 62)
        print("probes=%s fmt=%d" % (probes, fmt))
        print(txt[:3000] if isinstance(txt, str) else repr(txt)[:3000])

sys.stdout.flush()
os._exit(0)
