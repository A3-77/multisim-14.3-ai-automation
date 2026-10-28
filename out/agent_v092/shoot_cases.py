# -*- coding: utf-8 -*-
"""对三个 Case 的 circuit.ms14 各抓一组真实 Multisim GUI 截图。

全部走项目已有入口 screenshot.capture_schematic / capture_simulation，
不自己画图、不用 GetCircuitImage 冒充。
"""
import json
import os
import sys

ROOT = r"C:\Users\A377\WorkBuddy AI\ni\multisim-ctrl"
sys.path.insert(0, os.path.join(ROOT, "tools"))
import screenshot as SS  # noqa: E402

JOBS = [
    ("case_a_rc", "0.005"),
    ("case_b_rectifier", "0.1"),
    ("case_c_iterative", "0.005"),
]

res = {}
for case, tstop in JOBS:
    d = os.path.join(ROOT, "out", "agent_v092", case)
    ms14 = os.path.join(d, "circuit.ms14")
    one = {}
    try:
        r = SS.capture_schematic(ms14, os.path.join(d, "01_schematic.png"))
        one["schematic"] = {k: r[k] for k in ("width", "height", "content_ok", "method")}
        print("[%s] schematic %dx%d content_ok=%s"
              % (case, r["width"], r["height"], r["content_ok"]), flush=True)
    except Exception as e:
        one["schematic"] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        print("[%s] schematic FAILED %s" % (case, e), flush=True)

    try:
        r = SS.capture_simulation(ms14, os.path.join(d, "02_simulation.png"), tstop=tstop)
        one["simulation"] = {k: r[k] for k in ("width", "height", "method")}
        one["simulation"]["params"] = r["params"]
        print("[%s] simulation %dx%d tstop=%s" % (case, r["width"], r["height"], tstop),
              flush=True)
    except Exception as e:
        one["simulation"] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        print("[%s] simulation FAILED %s" % (case, e), flush=True)

    res[case] = one

with open(os.path.join(ROOT, "out", "agent_v092", "screenshot_report.json"), "w",
          encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print(json.dumps(res, ensure_ascii=False, indent=2))
