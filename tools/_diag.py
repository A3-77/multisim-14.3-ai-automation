# -*- coding: utf-8 -*-
"""诊断：不调 Connect() 能否直接用；以及 Connect 失败的具体原因。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

CIRCUIT = os.path.join(ROOT, "out", "ref", "with_probes.ms14")

print("--- A: Dispatch only, no Connect ---")
try:
    app = msc.Dispatch(msc.PROGID)
    print("  Dispatch ok:", app)
    try:
        print("  VersionInfo:", app.VersionInfo)
    except Exception as e:
        print("  VersionInfo failed:", repr(e))
    try:
        print("  IsConnected:", app.IsConnected)
    except Exception as e:
        print("  IsConnected failed:", repr(e))
    try:
        c = app.OpenFile(os.path.abspath(CIRCUIT))
        print("  OpenFile ok:", c.CircuitName)
        print("  EnumComponents:", c.EnumComponents(0))
        print("  RLCValue(R1):", c.RLCValue("R1"))
        print("  EnumOutputs(0):", c.EnumOutputs(0))
    except Exception as e:
        print("  OpenFile failed:", repr(e))
except Exception as e:
    print("  Dispatch failed:", repr(e))

print("\n--- B: retry Connect a few times ---")
for i in range(3):
    try:
        app2 = msc.Dispatch(msc.PROGID)
        app2.Connect()
        print("  attempt %d: Connect ok" % i)
        break
    except Exception as e:
        print("  attempt %d: %r" % (i, e))
        time.sleep(5)

print("\nDONE-DIAG")
os._exit(0)
