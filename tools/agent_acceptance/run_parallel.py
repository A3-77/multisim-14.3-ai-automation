# -*- coding: utf-8 -*-
"""v0.10.0 Agent 验收：同一节点 2 个到地元件（parallel_shunt）从 MCP 到真机。

**这个脚本不 import 任何项目模块。** 它只做两件事：
  1. 用 `agent_cli.py` 起独立进程调 MCP 工具（Agent 唯一的入口）
  2. 拿工具返回的 CSV 自己用 DFT 复算一遍（不信任项目自己的 theory）

两个 Case：

  A · RC 并联负载    V1(1V/1kHz) - R1(1k) - n1，n1 上 C1(159.155nF) ∥ R2(1k) 下地
                    理论 |H| = 0.4472136，∠H = -26.5651°
                    （Z_C = 1kΩ → Z_par = 500-j500 → H = 0.44721∠-26.565°）
                    这一例是**电气**验证：两个到地元件必须都在网表里，
                    少一个增益就变成 0.7071（只剩 C）或 0.5（只剩 R）。

  B · 分压 + 旁路电容 V1(5V DC) - R1(1k) - n1，n1 上 R2(1k) ∥ C1(100nF) 下地
                    理论：直流下电容开路，n1 = 2.5V
                    这一例是**几何**验证：DC 工作点对导线穿符号最敏感 ——
                    v0.7.0 就是因为导线横穿电阻符号，Multisim 只认出一个通道。

跑法：
    runtime\\py32\\python.exe tools/agent_acceptance/run_parallel.py
"""
import cmath
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
CLI = os.path.join(HERE, "agent_cli.py")
WD = os.path.join(ROOT, "out", "agent_v10", "parallel")

FREQ = 1000.0
C_FOR_1K = 1.0 / (2.0 * math.pi * FREQ * 1000.0)     # ≈ 159.1549 nF

CALLS = []
FAILS = []


def ok(name, cond, detail=""):
    if cond:
        print("  %-54s OK   %s" % (name, detail))
    else:
        FAILS.append(name)
        print("  %-54s FAIL %s" % (name, detail))
    return cond


def mcp(tool, args=None):
    args = args or {}
    t0 = time.time()
    p = subprocess.run([PY, CLI, "--workdir", WD, "call", tool,
                        json.dumps(args, ensure_ascii=False)],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    dt = time.time() - t0
    try:
        r = json.loads(p.stdout)
    except Exception:
        print("  !! %s 返回不是 JSON\n%s\n%s"
              % (tool, p.stdout[:800], p.stderr[:800]))
        raise
    rec = {"tool": tool, "args": args, "elapsed": round(dt, 2),
           "ok": bool(r.get("ok")), "result": r}
    CALLS.append(rec)
    extra = ""
    if not rec["ok"]:
        e = r.get("error") or {}
        extra = "%s | %s" % (e.get("code"), (e.get("message") or "")[:90])
    print("  [%5.1fs] %-14s %s  %s"
          % (dt, tool, "OK" if rec["ok"] else "ERR", extra))
    return r


def tools_list():
    p = subprocess.run([PY, CLI, "--workdir", WD, "tools"],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return json.loads(p.stdout)


# ---------------------------------------------------------------------------
# 独立复算：只读 CSV，用 DFT 单频投影，不 import 项目代码
# ---------------------------------------------------------------------------
def read_csv(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head = rows[0][1:]
    t, cols = [], {h: [] for h in head}
    for r in rows[1:]:
        if not r:
            continue
        t.append(float(r[0]))
        for i, h in enumerate(head, 1):
            cols[h].append(float(r[i]))
    return t, cols


def phasor(t, v, f):
    """单频 DFT 投影：v(t) ≈ A·cos(2πft) + B·sin(2πft) → 复相量 A-jB。

    只用整周期采样时这是精确的（正交性成立）；本脚本的窗口是整数个周期。
    """
    a = b = 0.0
    n = len(v)
    for ti, vi in zip(t, v):
        w = 2.0 * math.pi * f * ti
        a += vi * math.cos(w)
        b += vi * math.sin(w)
    a *= 2.0 / n
    b *= 2.0 / n
    return complex(a, -b)


def recompute_ac(path, probe_of):
    """稳态增益 / 相位。**跳过前 2 个周期** —— 那是电容充电的启动暂态。

    这一点是实测出来的，不是想当然：同一个 CSV 全窗口算出来相位 −26.266°，
    跳过前 2 周期是 −26.645°，差 0.38°；而 Multisim 稳态理论值（复数分压）是
    −26.565°，也就是**跳过暂态后误差从 0.30° 降到 0.08°**。
    两个窗口的结果都返回，让报告能自己证明"暂态确实存在"。
    """
    t, cols = read_csv(path)
    vin = cols[probe_of["P_in"]]
    vout = cols[probe_of["P_out"]]

    period = 1.0 / FREQ
    i0 = 0
    while i0 < len(t) and t[i0] < 2.0 * period - 1e-12:
        i0 += 1

    def one(a):
        hi = phasor(t[a:], vin[a:], FREQ)
        ho = phasor(t[a:], vout[a:], FREQ)
        h = ho / hi
        return {"n": len(t) - a, "vin_amp": abs(hi), "vout_amp": abs(ho),
                "gain": abs(h), "phase_deg": math.degrees(cmath.phase(h))}

    steady = one(i0)
    steady.update({
        "t_range": [t[i0], t[-1]],
        "skipped_periods": 2,
        "mean_out": sum(vout) / len(vout),
        "full_window": one(0),        # 含启动暂态，用来对照
    })
    return steady


def recompute_dc(path, probe_of):
    t, cols = read_csv(path)
    v = cols[probe_of["P_out"]]
    return {"n": len(v), "mean": sum(v) / len(v),
            "min": min(v), "max": max(v)}


# ---------------------------------------------------------------------------
def case_a():
    print("\n" + "=" * 78)
    print("Case A · RC 并联负载（AC 1V / 1kHz）")
    print("=" * 78)

    r = mcp("create_circuit", {"name": "rc_parallel"})
    cid = r.get("circuit_id")
    ok("create_circuit", bool(cid), str(cid))

    mcp("add_component", {"circuit_id": cid,
                          "family": "SIGNAL_VOLTAGE_SOURCES",
                          "part": "AC_VOLTAGE", "refdes": "V1",
                          "value": 1.0, "parameters": {"frequency": FREQ}})
    mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                          "part": "RESISTOR_VIRTUAL", "refdes": "R1",
                          "value": 1000.0})
    mcp("add_component", {"circuit_id": cid, "family": "CAPACITOR",
                          "part": "CAPACITOR_VIRTUAL", "refdes": "C1",
                          "value": C_FOR_1K})
    mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                          "part": "RESISTOR_VIRTUAL", "refdes": "R2",
                          "value": 1000.0})
    mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                          "part": "GROUND", "refdes": "GND1"})

    mcp("connect", {"circuit_id": cid, "pins": [["V1", "+"], ["R1", "1"]],
                    "net": "in"})
    mcp("connect", {"circuit_id": cid,
                    "pins": [["R1", "2"], ["C1", "1"], ["R2", "1"]],
                    "net": "n1"})
    r = mcp("connect", {"circuit_id": cid,
                        "pins": [["C1", "2"], ["R2", "2"], ["V1", "-"],
                                 ["GND1", "1"]], "net": "0"})
    topo = r.get("topology") or {}
    ok("拓扑判成 parallel_shunt", topo.get("kind") == "parallel_shunt",
       str(topo.get("kind")))
    ok("topology.supported=True", topo.get("supported") is True,
       str(topo.get("reason")))
    ok("n_shunt = 2（数元件）", topo.get("n_shunt") == 2,
       str(topo.get("n_shunt")))
    shunts = ((topo.get("stages") or [{}, {}])[1] or {}).get("shunts")
    ok("两个到地元件都记在 n1 那一级", shunts == ["C1", "R2"], str(shunts))

    mcp("add_probe", {"circuit_id": cid, "target": "in", "name": "P_in"})
    r = mcp("add_probe", {"circuit_id": cid, "target": "n1", "name": "P_out"})
    ok("complete=True", (r.get("topology") or {}).get("complete") is True,
       str((r.get("topology") or {}).get("issues")))

    r = mcp("simulate", {"circuit_id": cid, "analysis": "transient",
                         "start": 0.0, "stop": 0.01, "sample_rate": 200000,
                         "timeout": 300})
    ok("simulate 成功", r.get("ok"), str((r.get("error") or {}).get("code") or ""))
    sim_id = r.get("sim_id")
    outs = r.get("outputs") or []
    ok("**两个探针都注册上了**", len(outs) == 2, str(outs))
    ok("采样点够（10 个周期 @ 200kHz）", (r.get("n") or 0) >= 2000,
       str(r.get("n")))

    ms14 = r.get("ms14")
    ms14_fixed = os.path.join(WD, "case_a_rc_parallel.ms14")
    if ms14:
        src = ms14 if os.path.isabs(ms14) else os.path.join(ROOT, ms14)
        if os.path.isfile(src):
            shutil.copy2(src, ms14_fixed)

    r = mcp("measure", {"sim_id": sim_id, "what": "all"})
    ok("measure 成功", r.get("ok"))
    ok("mode=ratio（拓扑配对成功）", r.get("mode") == "ratio", str(r.get("mode")))
    th = r.get("theory") or {}
    g_theory = th.get("gain")
    p_theory = th.get("phase_deg")
    print("     实测 gain     = %s" % r.get("gain"))
    print("     实测 phase    = %s" % r.get("phase_deg"))
    print("     理论 kind     = %s  gain=%.7f  phase=%.5f°"
          % (th.get("kind"), g_theory or 0, p_theory or 0))
    ok("theory 是 ac_ladder（v0.10.0 新增的解析解）",
       th.get("kind") == "ac_ladder", str(th.get("kind")))
    ok("theory.topology = parallel_shunt",
       th.get("topology") == "parallel_shunt", str(th.get("topology")))
    ok("理论增益 = 0.4472136",
       g_theory is not None and abs(g_theory - 0.4472136) < 1e-6,
       "%.7f" % (g_theory or 0))
    ok("理论相位 = -26.5651°",
       p_theory is not None and abs(p_theory + 26.56505) < 1e-4,
       "%.5f°" % (p_theory or 0))

    r = mcp("get_waveform", {"sim_id": sim_id, "max_points": 8})
    ok("get_waveform 成功", r.get("ok"))
    csv_rel = r.get("artifact")
    probe_of = {p.get("probe_id"): p.get("output")
                for p in (r.get("probes") or [])}
    csv_fixed = os.path.join(WD, "case_a_rc_parallel.csv")
    src = (csv_rel if os.path.isabs(csv_rel) else os.path.join(ROOT, csv_rel)) \
        if csv_rel else None
    if src and os.path.isfile(src):
        shutil.copy2(src, csv_fixed)

    print("\n  --- 独立复算（DFT 单频投影，不 import 项目代码）---")
    rec = recompute_ac(csv_fixed, probe_of)
    fw = rec["full_window"]
    print("     稳态（跳过前 2 周期）: gain = %.7f  phase = %.5f°  (n=%d)"
          % (rec["gain"], rec["phase_deg"], rec["n"]))
    print("     全窗口（含启动暂态）  : gain = %.7f  phase = %.5f°  (n=%d)"
          % (fw["gain"], fw["phase_deg"], fw["n"]))
    ok("复算增益与理论差 < 0.5%",
       abs(rec["gain"] - 0.4472136) / 0.4472136 < 0.005,
       "%.7f" % rec["gain"])
    ok("复算相位与理论差 < 0.2°",
       abs(rec["phase_deg"] + 26.56505) < 0.2,
       "%.5f°" % rec["phase_deg"])
    ok("输入幅度 = 1V（源没被衰减）", abs(rec["vin_amp"] - 1.0) < 0.005,
       "%.5f" % rec["vin_amp"])
    ok("**启动暂态确实存在**（含暂态的相位偏离稳态 > 0.2°）",
       abs(fw["phase_deg"] - rec["phase_deg"]) > 0.2,
       "%.4f° vs %.4f°" % (fw["phase_deg"], rec["phase_deg"]))
    if r.get("gain") is not None:
        ok("measure 的 gain 与独立复算一致",
           abs(r["gain"] - rec["gain"]) < 1e-3,
           "差 %.2e" % abs(r["gain"] - rec["gain"]))
        ok("measure 的 phase 与独立复算一致",
           abs(r["phase_deg"] - rec["phase_deg"]) < 1e-3,
           "差 %.2e°" % abs(r["phase_deg"] - rec["phase_deg"]))

    # 反证：如果只有 C1 在网表里，增益会是 0.7071；只有 R2，则是 0.5
    ok("**增益既不是 0.7071（少 R2）也不是 0.5（少 C1）**",
       abs(rec["gain"] - 0.7071068) > 0.01 and abs(rec["gain"] - 0.5) > 0.01,
       "%.5f" % rec["gain"])

    return {"circuit_id": cid, "sim_id": sim_id, "measure": r,
            "recompute": rec, "theory": th,
            "ms14": os.path.relpath(ms14_fixed, ROOT)
            if os.path.isfile(ms14_fixed) else None,
            "csv": os.path.relpath(csv_fixed, ROOT)
            if os.path.isfile(csv_fixed) else None}


def case_b():
    print("\n" + "=" * 78)
    print("Case B · 分压 + 旁路电容（DC 5V）—— 几何验证")
    print("=" * 78)

    r = mcp("create_circuit", {"name": "divider_bypass"})
    cid = r.get("circuit_id")
    ok("create_circuit", bool(cid), str(cid))

    mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                          "part": "DC_POWER", "refdes": "V1", "value": 5.0})
    mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                          "part": "RESISTOR_VIRTUAL", "refdes": "R1",
                          "value": 1000.0})
    mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                          "part": "RESISTOR_VIRTUAL", "refdes": "R2",
                          "value": 1000.0})
    mcp("add_component", {"circuit_id": cid, "family": "CAPACITOR",
                          "part": "CAPACITOR_VIRTUAL", "refdes": "C1",
                          "value": 100e-9})
    mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                          "part": "GROUND", "refdes": "GND1"})

    mcp("connect", {"circuit_id": cid, "pins": [["V1", "+"], ["R1", "1"]],
                    "net": "in"})
    mcp("connect", {"circuit_id": cid,
                    "pins": [["R1", "2"], ["R2", "1"], ["C1", "1"]],
                    "net": "n1"})
    r = mcp("connect", {"circuit_id": cid,
                        "pins": [["R2", "2"], ["C1", "2"], ["V1", "-"],
                                 ["GND1", "1"]], "net": "0"})
    topo = r.get("topology") or {}
    ok("拓扑判成 parallel_shunt", topo.get("kind") == "parallel_shunt",
       str(topo.get("kind")))

    r = mcp("add_probe", {"circuit_id": cid, "target": "n1", "name": "P_out"})
    ok("complete=True", (r.get("topology") or {}).get("complete") is True,
       str((r.get("topology") or {}).get("issues")))

    r = mcp("simulate", {"circuit_id": cid, "analysis": "dc", "timeout": 300})
    ok("simulate(dc) 成功", r.get("ok"),
       str((r.get("error") or {}).get("code") or ""))
    sim_id = r.get("sim_id")
    outs = r.get("outputs") or []
    ok("探针注册上了", len(outs) == 1, str(outs))

    ms14 = r.get("ms14")
    ms14_fixed = os.path.join(WD, "case_b_divider_bypass.ms14")
    if ms14:
        src = ms14 if os.path.isabs(ms14) else os.path.join(ROOT, ms14)
        if os.path.isfile(src):
            shutil.copy2(src, ms14_fixed)

    r = mcp("measure", {"sim_id": sim_id, "what": "all"})
    ok("measure 成功", r.get("ok"))
    chans = r.get("channels") or {}
    v = next(iter(chans.values()), {}) if chans else {}
    print("     实测 n1 均值 = %s" % v.get("mean"))
    ok("直流工作点 = 2.5V（电容开路，不影响分压）",
       v.get("mean") is not None and abs(v["mean"] - 2.5) < 0.002,
       "%.6f V" % (v.get("mean") or 0))

    r2 = mcp("get_waveform", {"sim_id": sim_id, "max_points": 4})
    csv_rel = r2.get("artifact")
    probe_of = {p.get("probe_id"): p.get("output")
                for p in (r2.get("probes") or [])}
    csv_fixed = os.path.join(WD, "case_b_divider_bypass.csv")
    src = (csv_rel if os.path.isabs(csv_rel) else os.path.join(ROOT, csv_rel)) \
        if csv_rel else None
    if src and os.path.isfile(src):
        shutil.copy2(src, csv_fixed)

    rec = None
    if os.path.isfile(csv_fixed):
        rec = recompute_dc(csv_fixed, probe_of)
        print("     复算 n1 均值 = %.6f V (min=%.6f max=%.6f n=%d)"
              % (rec["mean"], rec["min"], rec["max"], rec["n"]))
        ok("复算直流工作点 = 2.5V", abs(rec["mean"] - 2.5) < 0.002,
           "%.6f V" % rec["mean"])
        ok("读数不是常数噪声（min 与 max 之差 < 1mV）",
           rec["max"] - rec["min"] < 1e-3,
           "%.2e V" % (rec["max"] - rec["min"]))

    return {"circuit_id": cid, "sim_id": sim_id, "measure": r,
            "recompute": rec,
            "ms14": os.path.relpath(ms14_fixed, ROOT)
            if os.path.isfile(ms14_fixed) else None,
            "csv": os.path.relpath(csv_fixed, ROOT)
            if os.path.isfile(csv_fixed) else None}


def main():
    os.makedirs(WD, exist_ok=True)
    trace = os.path.join(WD, "trace.jsonl")
    if os.path.isfile(trace):
        os.remove(trace)

    print("=" * 78)
    print("v0.10.0 Agent 验收：同一节点 2 个到地元件（parallel_shunt）")
    print("workdir: %s" % WD)
    print("=" * 78)

    print("\n[0] Agent 只能看到 tools/list")
    tl = tools_list()
    names = [t["name"] for t in tl.get("tools", [])]
    ok("8 个工具都在", len(names) == 8, ", ".join(names))

    a = case_a()
    b = case_b()

    errs = [c for c in CALLS if not c["ok"]]
    print("\n" + "=" * 78)
    print("工具调用 %d 次，失败 %d 次，总耗时 %.1f s"
          % (len(CALLS), len(errs), sum(c["elapsed"] for c in CALLS)))
    print("断言失败 %d 项" % len(FAILS))
    for f in FAILS:
        print("  - %s" % f)
    print("=" * 78)

    summary = {
        "version": "v0.10.0",
        "case_a": {k: v for k, v in a.items() if k != "measure"},
        "case_b": {k: v for k, v in b.items() if k != "measure"},
        "calls": [{"tool": c["tool"], "ok": c["ok"], "elapsed": c["elapsed"]}
                  for c in CALLS],
        "n_calls": len(CALLS), "n_errors": len(errs),
        "total_s": round(sum(c["elapsed"] for c in CALLS), 1),
        "fails": FAILS, "pass": not FAILS,
    }
    with open(os.path.join(WD, "acceptance.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("报告: %s" % os.path.join(WD, "acceptance.json"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
