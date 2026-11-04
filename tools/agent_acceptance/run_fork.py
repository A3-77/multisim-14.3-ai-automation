# -*- coding: utf-8 -*-
"""v0.11.0 Agent 验收：分叉树（一个节点两条主干）从 MCP 到真机。

**这个脚本不 import 任何项目模块。** 它只做两件事：
  1. 用 `agent_cli.py` 起独立进程调 MCP 工具（Agent 唯一的入口）
  2. 拿工具返回的 CSV 自己用 DFT 复算一遍（不信任项目自己的 theory）

两个 Case：

  A · 两组 RC 并联    V1(1V/1kHz) - in ─┬─ R1(1k)  - n1 - C1(159.155nF) - GND
                                        └─ R2(2k)  - n2 - C2(159.155nF) - GND
                     支路 1：fc = 1kHz  -> |H| = 1/√2 = 0.7071068，∠-45.0000°
                     支路 2：fc = 500Hz -> |H| = 1/√5 = 0.4472136，∠-63.4349°
                     这一例是**电气**验证：两条支路的增益必须各算各的。
                     如果 R2/C2 被漏掉、或者两条支路被短接成一条，两个读数
                     会同时变成同一个值 —— 那是很容易看出来的。

  B · 分叉 + 多级    V1(5V DC) - R1(1k) - n1 ─┬─ R2(1k) - n2 - R4(1k) - GND
                                              └─ R3(1k) - n3 - R5(1k) - GND
                     理论：n1 = 2.5V，n2 = n3 = 1.25V
                     （两条 2k 支路并联 = 1k，与 R1 分压；每个节点再对半）
                     这一例是**几何**验证：DC 工作点对"导线穿符号"最敏感
                     （v0.7.0 就是因此只认出一个通道），而且分叉 + 两级串联
                     会把泳道排布的每个坑都走一遍。

跑法：
    runtime\\py32\\python.exe tools/agent_acceptance/run_fork.py
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
WD = os.path.join(ROOT, "out", "agent_v11", "fork")

FREQ = 1000.0
C_FOR_1K = 1.0 / (2.0 * math.pi * FREQ * 1000.0)     # ≈ 159.1549 nF

# Case A 的两条支路理论值（手算，不调项目代码）
A1_GAIN = 1.0 / math.sqrt(2.0)                        # 0.70710678
A1_PHASE = -45.0
A2_GAIN = 1.0 / math.sqrt(5.0)                        # 0.44721360
A2_PHASE = -math.degrees(math.atan(2.0))              # -63.43495

CALLS = []
FAILS = []


def ok(name, cond, detail=""):
    if cond:
        print("  %-56s OK   %s" % (name, detail))
    else:
        FAILS.append(name)
        print("  %-56s FAIL %s" % (name, detail))
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
    """单频 DFT 投影：v(t) ≈ A·cos(2πft) + B·sin(2πft) → 复相量 A-jB。"""
    a = b = 0.0
    n = len(v)
    for ti, vi in zip(t, v):
        w = 2.0 * math.pi * f * ti
        a += vi * math.cos(w)
        b += vi * math.sin(w)
    a *= 2.0 / n
    b *= 2.0 / n
    return complex(a, -b)


def recompute_ac(path, out_probe, probe_of, in_probe="P_in"):
    """稳态增益 / 相位（跳过前 2 个周期的启动暂态），同时保留全窗口对照。

    `probe_of` 是 {probe_id: CSV 列名} —— CSV 的列名是 Multisim 的输出名
    （`V(探针1)`），不是 IR 里的位号。
    """
    t, cols = read_csv(path)
    vin = cols[probe_of[in_probe]]
    vout = cols[probe_of[out_probe]]

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
    steady.update({"t_range": [t[i0], t[-1]], "skipped_periods": 2,
                   "full_window": one(0)})
    return steady


def recompute_dc(path, probe, probe_of):
    t, cols = read_csv(path)
    v = cols[probe_of[probe]]
    return {"n": len(v), "mean": sum(v) / len(v), "min": min(v), "max": max(v)}


# ---------------------------------------------------------------------------
def case_a():
    print("\n" + "=" * 80)
    print("Case A · 两组 RC 并联（AC 1V / 1kHz）—— 两条支路必须各算各的")
    print("=" * 80)

    r = mcp("create_circuit", {"name": "fork_rc_pair"})
    cid = r.get("circuit_id")
    ok("create_circuit", bool(cid), str(cid))

    for ref, fam, part, val, extra in (
            ("V1", "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", 1.0,
             {"frequency": FREQ}),
            ("R1", "RESISTOR", "RESISTOR_VIRTUAL", 1000.0, None),
            ("C1", "CAPACITOR", "CAPACITOR_VIRTUAL", C_FOR_1K, None),
            ("R2", "RESISTOR", "RESISTOR_VIRTUAL", 2000.0, None),
            ("C2", "CAPACITOR", "CAPACITOR_VIRTUAL", C_FOR_1K, None),
            ("GND1", "POWER_SOURCES", "GROUND", None, None)):
        args = {"circuit_id": cid, "family": fam, "part": part, "refdes": ref}
        if val is not None:
            args["value"] = val
        if extra:
            args["parameters"] = extra
        mcp("add_component", args)

    mcp("connect", {"circuit_id": cid, "pins": [["V1", "+"], ["R1", "1"],
                                                ["R2", "1"]], "net": "in"})
    mcp("connect", {"circuit_id": cid, "pins": [["R1", "2"], ["C1", "1"]],
                    "net": "n1"})
    mcp("connect", {"circuit_id": cid, "pins": [["R2", "2"], ["C2", "1"]],
                    "net": "n2"})
    r = mcp("connect", {"circuit_id": cid,
                        "pins": [["C1", "2"], ["C2", "2"], ["V1", "-"],
                                 ["GND1", "1"]], "net": "0"})
    topo = r.get("topology") or {}
    ok("拓扑判成 parallel_branch", topo.get("kind") == "parallel_branch",
       str(topo.get("kind")))
    ok("topology.supported=True", topo.get("supported") is True,
       str(topo.get("reason")))
    ok("paths 认出 2 条通路", len(topo.get("paths") or []) == 2,
       str(topo.get("paths")))
    ok("forks 指出分叉点在 in",
       (topo.get("forks") or [{}])[0].get("net") == "in",
       str(topo.get("forks")))
    ok("n_series=2 / n_shunt=2",
       (topo.get("n_series"), topo.get("n_shunt")) == (2, 2),
       "%s/%s" % (topo.get("n_series"), topo.get("n_shunt")))

    mcp("add_probe", {"circuit_id": cid, "target": "in", "name": "P_in"})
    mcp("add_probe", {"circuit_id": cid, "target": "n1", "name": "P_n1"})
    r = mcp("add_probe", {"circuit_id": cid, "target": "n2", "name": "P_n2"})
    ok("complete=True", (r.get("topology") or {}).get("complete") is True,
       str((r.get("topology") or {}).get("issues")))

    r = mcp("simulate", {"circuit_id": cid, "analysis": "transient",
                         "start": 0.0, "stop": 0.01, "sample_rate": 200000,
                         "timeout": 300})
    ok("simulate 成功", r.get("ok"),
       str((r.get("error") or {}).get("code") or ""))
    sim_id = r.get("sim_id")
    outs = r.get("outputs") or []
    ok("**三个探针都注册上了**（分叉处没有导线压引脚）", len(outs) == 3,
       str(outs))

    ms14 = r.get("ms14")
    ms14_fixed = os.path.join(WD, "case_a_fork_rc_pair.ms14")
    if ms14:
        src = ms14 if os.path.isabs(ms14) else os.path.join(ROOT, ms14)
        if os.path.isfile(src):
            shutil.copy2(src, ms14_fixed)

    r = mcp("get_waveform", {"sim_id": sim_id, "max_points": 8})
    ok("get_waveform 成功", r.get("ok"))
    csv_rel = r.get("artifact")
    probe_of = {p.get("probe_id"): p.get("output")
                for p in (r.get("probes") or [])}
    csv_fixed = os.path.join(WD, "case_a_fork_rc_pair.csv")
    src = (csv_rel if os.path.isabs(csv_rel) else os.path.join(ROOT, csv_rel)) \
        if csv_rel else None
    if src and os.path.isfile(src):
        shutil.copy2(src, csv_fixed)

    res = {}
    print("\n  --- 独立复算（DFT 单频投影，不 import 项目代码）---")
    for probe, g_th, p_th, label in (
            ("P_n1", A1_GAIN, A1_PHASE, "支路 1 R1+C1 (fc=1kHz)"),
            ("P_n2", A2_GAIN, A2_PHASE, "支路 2 R2+C2 (fc=500Hz)")):
        rec = recompute_ac(csv_fixed, probe, probe_of)
        fw = rec["full_window"]
        print("     %-26s gain = %.7f  phase = %.5f°  (n=%d)"
              % (label, rec["gain"], rec["phase_deg"], rec["n"]))
        print("     %-26s 全窗口对照 gain = %.7f  phase = %.5f°"
              % ("", fw["gain"], fw["phase_deg"]))
        ok("%s 增益 = %.7f（差 < 0.5%%）" % (label, g_th),
           abs(rec["gain"] - g_th) / g_th < 0.005, "%.7f" % rec["gain"])
        ok("%s 相位 = %.4f°（差 < 0.5°）" % (label, p_th),
           abs(rec["phase_deg"] - p_th) < 0.5, "%.5f°" % rec["phase_deg"])
        res[probe] = rec

    # 反证：两条支路不能给出同一个读数
    ok("**两条支路读数不同**（不是把两条支路短成了一条）",
       abs(res["P_n1"]["gain"] - res["P_n2"]["gain"]) > 0.1,
       "%.5f vs %.5f" % (res["P_n1"]["gain"], res["P_n2"]["gain"]))
    ok("输入幅度 = 1V（源没被衰减）",
       abs(res["P_n1"]["vin_amp"] - 1.0) < 0.005,
       "%.5f" % res["P_n1"]["vin_amp"])

    # measure 也跑一次：Agent 会用它，不能因为树形拓扑就报错
    r = mcp("measure", {"sim_id": sim_id, "what": "all"})
    ok("measure 在树形拓扑下不报错", r.get("ok"),
       str((r.get("error") or {}).get("code") or ""))
    th = r.get("theory") or {}
    print("     measure.theory.kind = %s  n_paths = %s"
          % (th.get("kind"), th.get("n_paths")))
    ok("theory 是 ac_tree", th.get("kind") == "ac_tree", str(th.get("kind")))
    ok("theory 给出 2 条通路的理论值", th.get("n_paths") == 2,
       str(th.get("n_paths")))

    return {"circuit_id": cid, "sim_id": sim_id, "recompute": res,
            "theory": th,
            "ms14": os.path.relpath(ms14_fixed, ROOT)
            if os.path.isfile(ms14_fixed) else None,
            "csv": os.path.relpath(csv_fixed, ROOT)
            if os.path.isfile(csv_fixed) else None}


def case_b():
    print("\n" + "=" * 80)
    print("Case B · 分叉 + 多级（DC 5V）—— 几何验证")
    print("=" * 80)

    r = mcp("create_circuit", {"name": "fork_dc_ladder"})
    cid = r.get("circuit_id")
    ok("create_circuit", bool(cid), str(cid))

    mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                          "part": "DC_POWER", "refdes": "V1", "value": 5.0})
    for ref in ("R1", "R2", "R3", "R4", "R5"):
        mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                              "part": "RESISTOR_VIRTUAL", "refdes": ref,
                              "value": 1000.0})
    mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                          "part": "GROUND", "refdes": "GND1"})

    mcp("connect", {"circuit_id": cid, "pins": [["V1", "+"], ["R1", "1"]],
                    "net": "in"})
    mcp("connect", {"circuit_id": cid,
                    "pins": [["R1", "2"], ["R2", "1"], ["R3", "1"]],
                    "net": "n1"})
    mcp("connect", {"circuit_id": cid, "pins": [["R2", "2"], ["R4", "1"]],
                    "net": "n2"})
    mcp("connect", {"circuit_id": cid, "pins": [["R3", "2"], ["R5", "1"]],
                    "net": "n3"})
    r = mcp("connect", {"circuit_id": cid,
                        "pins": [["R4", "2"], ["R5", "2"], ["V1", "-"],
                                 ["GND1", "1"]], "net": "0"})
    topo = r.get("topology") or {}
    ok("拓扑判成 parallel_branch", topo.get("kind") == "parallel_branch",
       str(topo.get("kind")))
    ok("树深 = 2（分叉后还有一级）", topo.get("depth") == 2,
       str(topo.get("depth")))

    mcp("add_probe", {"circuit_id": cid, "target": "n1", "name": "P_n1"})
    mcp("add_probe", {"circuit_id": cid, "target": "n2", "name": "P_n2"})
    r = mcp("add_probe", {"circuit_id": cid, "target": "n3", "name": "P_n3"})
    ok("complete=True", (r.get("topology") or {}).get("complete") is True,
       str((r.get("topology") or {}).get("issues")))

    r = mcp("simulate", {"circuit_id": cid, "analysis": "dc", "timeout": 300})
    ok("simulate(dc) 成功", r.get("ok"),
       str((r.get("error") or {}).get("code") or ""))
    sim_id = r.get("sim_id")
    outs = r.get("outputs") or []
    ok("**三个探针都注册上了**", len(outs) == 3, str(outs))

    ms14 = r.get("ms14")
    ms14_fixed = os.path.join(WD, "case_b_fork_dc_ladder.ms14")
    if ms14:
        src = ms14 if os.path.isabs(ms14) else os.path.join(ROOT, ms14)
        if os.path.isfile(src):
            shutil.copy2(src, ms14_fixed)

    r2 = mcp("get_waveform", {"sim_id": sim_id, "max_points": 4})
    csv_rel = r2.get("artifact")
    probe_of = {p.get("probe_id"): p.get("output")
                for p in (r2.get("probes") or [])}
    csv_fixed = os.path.join(WD, "case_b_fork_dc_ladder.csv")
    src = (csv_rel if os.path.isabs(csv_rel) else os.path.join(ROOT, csv_rel)) \
        if csv_rel else None
    if src and os.path.isfile(src):
        shutil.copy2(src, csv_fixed)

    res = {}
    for probe, want, label in (("P_n1", 2.5, "n1（分叉点）"),
                               ("P_n2", 1.25, "n2（上支路）"),
                               ("P_n3", 1.25, "n3（下支路）")):
        rec = recompute_dc(csv_fixed, probe, probe_of)
        print("     %-18s 实测 = %.6f V (min=%.6f max=%.6f n=%d)"
              % (label, rec["mean"], rec["min"], rec["max"], rec["n"]))
        ok("%s = %g V" % (label, want), abs(rec["mean"] - want) < 0.002,
           "%.6f V" % rec["mean"])
        ok("  %s 读数稳定（min/max 差 < 1mV）" % label,
           rec["max"] - rec["min"] < 1e-3,
           "%.2e V" % (rec["max"] - rec["min"]))
        res[probe] = rec

    return {"circuit_id": cid, "sim_id": sim_id, "recompute": res,
            "ms14": os.path.relpath(ms14_fixed, ROOT)
            if os.path.isfile(ms14_fixed) else None,
            "csv": os.path.relpath(csv_fixed, ROOT)
            if os.path.isfile(csv_fixed) else None}


def main():
    os.makedirs(WD, exist_ok=True)
    trace = os.path.join(WD, "trace.jsonl")
    if os.path.isfile(trace):
        os.remove(trace)

    print("=" * 80)
    print("v0.11.0 Agent 验收：分叉树（一个节点两条主干）")
    print("workdir: %s" % WD)
    print("=" * 80)

    print("\n[0] Agent 只能看到 tools/list")
    tl = tools_list()
    names = [t["name"] for t in tl.get("tools", [])]
    ok("8 个工具都在", len(names) == 8, ", ".join(names))

    a = case_a()
    b = case_b()

    errs = [c for c in CALLS if not c["ok"]]
    print("\n" + "=" * 80)
    print("工具调用 %d 次，失败 %d 次，总耗时 %.1f s"
          % (len(CALLS), len(errs), sum(c["elapsed"] for c in CALLS)))
    print("断言失败 %d 项" % len(FAILS))
    for f in FAILS:
        print("  - %s" % f)
    print("=" * 80)

    summary = {
        "version": "v0.11.0",
        "case_a": a, "case_b": b,
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
