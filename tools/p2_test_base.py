# -*- coding: utf-8 -*-
"""P2 步骤 1：把剥离后的基底压成 .ms14，用 COM 打开验证能否打开、元件是否为空。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402

PLAIN = os.path.join(ROOT, "out", "rev_base_stripped.xml")
DST = os.path.join(ROOT, "out", "p2_base.ms14")

xml = open(PLAIN, "rb").read()
n, body = dcl.write_ms14(DST, xml)
print("基底 -> %s（文件 %d 字节）" % (DST, n))

# ---- COM 验证 ----
sys.path.insert(0, ROOT)
import msc  # noqa: E402

res = {"file": os.path.relpath(DST, ROOT), "multisim_version": None,
       "components": [], "outputs": [], "error": None,
       "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

try:
    ms = msc.Multisim()
    res["multisim_version"] = ms.version
    print("Multisim :", ms.version)
    c = ms.open(DST)
    print("打开     :", c)
    res["components"] = list(c.components())
    print("元件     :", res["components"])
    res["outputs"] = list(c.probes())
    print("outputs  :", res["outputs"])
except Exception as e:
    res["error"] = "%r" % (e,)
    print("失败     :", repr(e))

import json
json.dump(res, open(os.path.join(ROOT, "out", "p2_base_test.json"), "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print("\nDONE-BASE")
os._exit(0)
