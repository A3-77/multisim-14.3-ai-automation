# -*- coding: utf-8 -*-
"""升级后能力复测 —— 一阶 RC 低通。

严格模拟 v0.8 的 Agent 行为：**每次工具调用起一个独立的 MCP 客户端进程**
（agent_cli.py 的设计），所以 Agent 只能靠 MCP 协议拿状态，不能 import 项目模块。
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
CLI = os.path.join(ROOT, "tools", "agent_acceptance", "agent_cli.py")
WD = os.environ.get("RC_WD") or os.path.join(ROOT, "out", "agent_v083", "p1")
if not os.path.isabs(WD):
    WD = os.path.join(ROOT, WD)
os.makedirs(WD, exist_ok=True)

SEQ = []


def call(tool, args=None):
    args = args or {}
    t0 = time.time()
    p = subprocess.run([PY, CLI, "--workdir", WD, "call", tool,
                        json.dumps(args, ensure_ascii=False)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.time() - t0
    try:
        r = json.loads(p.stdout)
    except Exception:
        print("  !! %s 返回不是 JSON\n%s\n%s" % (tool, p.stdout[:600], p.stderr[:600]))
        raise
    SEQ.append({"tool": tool, "args": args, "ok": r.get("ok", not r.get("is_error")),
                "elapsed": round(dt, 2), "result": r})
    print("  [%5.1fs] %-14s %s" % (dt, tool, "OK" if SEQ[-1]["ok"] else "ERR"))
    return r


def brief(r, *keys):
    out = {k: r.get(k) for k in keys if k in r}
    return json.dumps(out, ensure_ascii=False)[:300]


print("=== [0] tools/list ===")
p = subprocess.run([PY, CLI, "--workdir", WD, "tools"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
tl = json.loads(p.stdout)
names = [t["name"] for t in tl.get("tools", [])]
print("  工具数 %d: %s" % (len(names), ", ".join(names)))

print("\n=== [1] 建电路 ===")
r = call("create_circuit", {"name": "rc_lpf_500hz_v083"})
CID = r["circuit_id"]

print("\n=== [2] 放元件 ===")
call("add_component", {"circuit_id": CID, "family": "SIGNAL_VOLTAGE_SOURCES",
                       "part": "AC_VOLTAGE", "refdes": "V1", "value": 1.0,
                       "parameters": {"frequency": 1000}})
call("add_component", {"circuit_id": CID, "family": "RESISTOR",
                       "part": "RESISTOR_VIRTUAL", "refdes": "R1", "value": 1000})
call("add_component", {"circuit_id": CID, "family": "CAPACITOR",
                       "part": "CAPACITOR_VIRTUAL", "refdes": "C1", "value": 3.3e-07})
call("add_component", {"circuit_id": CID, "family": "POWER_SOURCES",
                       "part": "GROUND", "refdes": "GND1"})

print("\n=== [3] 接线 ===")
call("connect", {"circuit_id": CID, "pins": [["V1", "+"], ["R1", "1"]], "net": "in"})
call("connect", {"circuit_id": CID, "pins": [["R1", "2"], ["C1", "1"]], "net": "out"})
r = call("connect", {"circuit_id": CID, "pins": [["V1", "-"], ["C1", "2"], ["GND1", "1"]]})
print("     topology:", json.dumps(r.get("topology", {}), ensure_ascii=False)[:260])

print("\n=== [4] 探针（故意先加输出探针，验 v0.8 的配对修复）===")
call("add_probe", {"circuit_id": CID, "target": "out", "name": "P_out"})
call("add_probe", {"circuit_id": CID, "target": "in", "name": "P_in"})

print("\n=== [5] 仿真 ===")
r = call("simulate", {"circuit_id": CID, "analysis": "transient",
                      "start": 0.002, "stop": 0.006, "sample_rate": 200000, "timeout": 240})
SIM = r.get("sim_id")
print("     sim_id=%s status=%s n=%s" % (SIM, r.get("status"), r.get("n")))
print("     timing:", json.dumps(r.get("timing", {}), ensure_ascii=False))
print("     ms14  :", r.get("ms14"))
print("     csv   :", r.get("waveform"))

print("\n=== [6] 读数 ===")
r = call("measure", {"sim_id": SIM, "what": "all"})
print("     pairing:", json.dumps(r.get("pairing"), ensure_ascii=False))
for ch, v in (r.get("channels") or {}).items():
    print("     %-8s %s" % (ch, json.dumps(v, ensure_ascii=False)[:220]))

print("\n=== [7] 波形抽样 ===")
r = call("get_waveform", {"sim_id": SIM, "max_points": 8})
print("     preview_step:", r.get("preview_step"))

print("\n=== [8] 会话终态 ===")
r = call("get_circuit", {"circuit_id": CID})
print("     counts:", json.dumps(r.get("counts"), ensure_ascii=False))
print("     topo  :", json.dumps(r.get("topology", {}), ensure_ascii=False)[:200])

with open(os.path.join(WD, "rerun_summary.json"), "w", encoding="utf-8") as f:
    json.dump({"circuit_id": CID, "sim_id": SIM,
               "calls": [{"tool": s["tool"], "ok": s["ok"], "elapsed": s["elapsed"]} for s in SEQ]},
              f, ensure_ascii=False, indent=2)
print("\n完成。workdir=%s" % WD)
