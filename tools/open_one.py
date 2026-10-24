# -*- coding: utf-8 -*-
"""单独打开一个文件并报告结果（在子进程里跑，崩溃不影响主控）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import msc

path = sys.argv[1]
try:
    ms = msc.Multisim()
    cir = ms.open(path)
    n = len(cir.components())
    print("OK|%s|%d" % (cir.name, n))
    try:
        ms.disconnect()
    except Exception:
        pass
except Exception as e:
    print("FAIL|%r" % (e,))
    sys.stdout.flush()
    os._exit(2)
sys.stdout.flush()
os._exit(0)
