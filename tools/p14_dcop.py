# -*- coding: utf-8 -*-
"""P14f: 用 DC 工作点绕过电容，判定电阻是否导通。
用法: runtime\py32\python.exe tools\p14_dcop.py <ms14> <json>
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

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

res = {"file": SRC, "outputs": [], "dc": {}, "error": "", "rlc": {}}
ms = msc.Multisim()
c = ms.open(SRC)

try:
    res["outputs"] = list(c.probes())
    print("outputs:", res["outputs"])
except Exception as e:
    res["error"] += "probes:%r " % (e,)

for ref in ("R1", "R2", "C1", "V1", "V2"):
    try:
        res["rlc"][ref] = c.rlc(ref)
    except Exception:
        pass
print("rlc:", res["rlc"])

try:
    data = c.dc_op()
    for name, (t, v) in data.items():
        res["dc"][name] = {"n": len(v), "first": v[0] if v else None,
                           "last": v[-1] if v else None}
    print("dc_op:", res["dc"])
except Exception as e:
    res["error"] += "dc_op:%r " % (e,)
    print("dc_op 失败:", repr(e))

try:
    res["last_error"] = c.last_error or ""
except Exception:
    pass

json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.stdout.flush()
os._exit(0)
