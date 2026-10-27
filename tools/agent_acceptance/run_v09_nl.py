# -*- coding: utf-8 -*-
"""v0.9 Agent 验收（自然语言版）：只给一段需求，Agent 自己设计 → 仿真 → 验算。

和 `run_diode.py` 的区别
------------------------
`run_diode.py` 验的是"新元件能不能用"——元件、拓扑、参数都是给定值。
这个脚本验的是**设计能力**：需求里只有一句话，拓扑 / 参数 / 元件数 /
连接关系 / 探针位置 / 仿真参数六件事全由 Agent 自己定。

所以脚本里**没有**任何"标准答案"。`DESIGN` 下面那段注释是 Agent 的推理过程，
连同 `derive_design()` 里的算式一起，构成"它是算出来的，不是抄的"的证据。

需求（原文，逐字）
------------------
    设计一个 1kHz 正弦波输入的两级 RC 低通滤波器，要求截止频率约为 500Hz，
    输入幅值 1V。选择合适的常见电阻和电容参数，完成完整电路连接，
    进行瞬态仿真，测量输入/输出幅值、增益和相位，并将实际结果与理论值进行
    比较。如果误差合理则判定设计通过。最后在 Multisim 中打开生成的电路，
    调整视图使完整电路可见，并截取一张真实的 Multisim 原理图截图。

这个脚本不 import 任何项目模块。它只做三件事：
  1. 用 `agent_cli.py` 起独立进程调 MCP 工具（Agent 唯一入口，每次一个进程）
  2. 自己算理论值（MCP 在两级 RC 下 `theory` 是 None，见下面 `[6]`）
  3. 从 CSV 自己拟合一遍（不信 `measure` 的拟合结果）

跑法
----
    runtime\\py32\\python.exe tools/agent_acceptance/run_v09_nl.py
"""
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
WD = os.path.join(ROOT, "out", "agent_v09", "nl_design")

TASK = (
    "设计一个 1kHz 正弦波输入的两级 RC 低通滤波器，要求截止频率约为 500Hz，"
    "输入幅值 1V。选择合适的常见电阻和电容参数，完成完整电路连接，"
    "进行瞬态仿真，测量输入/输出幅值、增益和相位，并将实际结果与理论值进行比较。"
    "如果误差合理则判定设计通过。最后在 Multisim 中打开生成的电路，"
    "调整视图使完整电路可见，并截取一张真实的 Multisim 原理图截图。"
)

# 验收判据（Agent 自己定的，写死在报告里，跑之前就定了 —— 不是看到结果再调）
TOL_GAIN_PCT = 2.0      # 增益相对误差 ≤ 2%
TOL_PHASE_DEG = 2.0     # 相位绝对误差 ≤ 2°
TOL_FC_PCT = 5.0        # 截止频率相对误差 ≤ 5%

CALLS = []
FAILS = []
CHECKS = []


def ok(name, cond, detail="", group="A"):
    cond = bool(cond)
    CHECKS.append({"name": name, "pass": cond, "detail": str(detail), "group": group})
    if cond:
        print("  %-56s OK   %s" % (name, detail))
    else:
        FAILS.append(name)
        print("  %-56s FAIL %s" % (name, detail))
    return cond


def mcp(tool, args=None):
    """一次工具调用 = 一个独立进程。Agent 拿不到进程内状态。"""
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
        print("  !! %s 返回不是 JSON\n%s\n%s" % (tool, p.stdout[:800], p.stderr[:800]))
        raise
    rec = {"tool": tool, "args": args, "elapsed": round(dt, 2),
           "ok": bool(r.get("ok")), "result": r}
    CALLS.append(rec)
    tag = "OK" if rec["ok"] else "ERR"
    extra = ""
    if not rec["ok"]:
        e = r.get("error") or {}
        extra = "%s | %s" % (e.get("code"), (e.get("message") or "")[:80])
    print("  [%5.1fs] %-14s %s  %s" % (dt, tool, tag, extra))
    return r


def tools_list():
    p = subprocess.run([PY, CLI, "--workdir", WD, "tools"],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return json.loads(p.stdout)


# ---------------------------------------------------------------------------
# 第一步：Agent 的设计推导（这段是"设计"，不是"填空"）
# ---------------------------------------------------------------------------
def derive_design(r_ohm, c_f, f_test, vin):
    """从需求倒推参数，并把每一步都算出来留证。

    需求里的"截止频率约 500Hz"对**两级无源 RC** 是有歧义的：

      (a) 按单级算：每级 f0 = 1/(2πRC)，两级各自 500Hz
      (b) 按整体算：级联后整体 -3dB 点 = 500Hz

    两级直接级联（后级是前级的负载，没有缓冲）时
        H(s) = 1 / (1 + 3sRC + (sRC)^2)
    整体 -3dB 在 x = ωRC = 0.37424，比单级 f0 低得多。
    需求说的是"滤波器截止频率"，工程语义上指整体 -3dB，所以取 (b)。

    由此反解 RC：
        RC = 0.37424 / (2π * 500) = 1.1911e-4 s
    选 R = 12kΩ（E24 常见）、C = 10nF（最常见容值）：
        RC = 1.2e-4 s  ->  f3dB = 496.3 Hz（偏 -0.73%，在 5% 内）
    """
    x3 = math.sqrt((-7.0 + math.sqrt(49.0 + 4.0)) / 2.0)   # x^4 + 7x^2 - 1 = 0
    rc = r_ohm * c_f
    f3db = x3 / (2.0 * math.pi * rc)
    f0 = 1.0 / (2.0 * math.pi * rc)                        # 单级极点
    # 测试频率处的理论响应
    x = 2.0 * math.pi * f_test * rc
    re, im = 1.0 - x * x, 3.0 * x
    gain = 1.0 / math.hypot(re, im)
    phase = -math.degrees(math.atan2(im, re))
    return {
        "x_at_3db": x3, "rc": rc,
        "f0_per_stage": f0, "f3db_composite": f3db,
        "f3db_err_pct": (f3db - 500.0) / 500.0 * 100.0,
        "at_test_freq": {"f": f_test, "x": x,
                         "gain": gain, "phase_deg": phase,
                         "amp": vin * gain},
        # 反例：经典"10k + 33nF"是**单级** 482Hz 的组合，两级级联后差 64%
        "counter_example": {
            "r": 10000.0, "c": 33e-9,
            "f3db_if_two_stage": x3 / (2 * math.pi * 10000.0 * 33e-9),
            "note": "10k+33nF 单级 f0=482Hz 看着对，两级级联整体 -3dB 只有 180Hz",
        },
    }


# ---------------------------------------------------------------------------
# 第二步：独立复算（只读 CSV，不 import 项目模块）
# ---------------------------------------------------------------------------
def sine_fit(t, v, f):
    """整周期投影法拟合 amp / phase。等价于最小二乘，但不需要解矩阵。

    v ≈ A·cos(wt) + B·sin(wt)  ->  amp = hypot(A,B),  phase = atan2(-B, A)
    只在**整数个周期**上积分才严格正交，所以先按 f 裁窗口。
    """
    t0 = t[0]
    cycles = int((t[-1] - t0) * f)
    if cycles < 1:
        return None
    t_end = t0 + cycles / float(f)
    tt = [a for a in t if a <= t_end + 1e-15]
    vv = [b for a, b in zip(t, v) if a <= t_end + 1e-15]
    n = len(vv)
    if n < 20:
        return None
    w = 2.0 * math.pi * f
    a_c = sum(b * math.cos(w * a) for a, b in zip(tt, vv)) * 2.0 / n
    a_s = sum(b * math.sin(w * a) for a, b in zip(tt, vv)) * 2.0 / n
    return {"amp": math.hypot(a_c, a_s),
            "phase_deg": math.degrees(math.atan2(-a_s, a_c)),
            "n": n, "cycles": cycles, "window": [tt[0], tt[-1]]}


def recompute(csv_path, probe_of, f):
    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    head = rows[0][1:]
    cols = {h: [] for h in head}
    t = []
    for r in rows[1:]:
        if not r:
            continue
        t.append(float(r[0]))
        for i, h in enumerate(head, 1):
            cols[h].append(float(r[i]))

    c_in = probe_of.get("P_in")
    c_out = probe_of.get("P_out")
    if c_in not in cols or c_out not in cols:
        return {"error": "CSV 列对不上：期望 %r/%r，实际 %s"
                         % (c_in, c_out, head)}

    fi = sine_fit(t, cols[c_in], f)
    fo = sine_fit(t, cols[c_out], f)
    if not fi or not fo:
        return {"error": "窗口不足一个周期"}

    gain = fo["amp"] / fi["amp"]
    d = fo["phase_deg"] - fi["phase_deg"]
    while d > 180:
        d -= 360
    while d < -180:
        d += 360
    return {"n": len(t), "t_range": [t[0], t[-1]],
            "in": fi, "out": fo,
            "gain": gain, "phase_deg": d}


def main():
    os.makedirs(WD, exist_ok=True)
    trace = os.path.join(WD, "trace.jsonl")
    if os.path.isfile(trace):
        os.remove(trace)

    print("=" * 80)
    print("v0.9 Agent 验收（自然语言 → 设计 → 仿真 → 验算 → 截图）")
    print("workdir: %s" % WD)
    print("=" * 80)
    print("\n需求原文：\n  %s\n" % TASK)

    # ---------------- 0) tools/list：先看 Agent 手里有什么 ----------------
    print("[0] Agent 只能看到 tools/list")
    tl = tools_list()
    names = [t["name"] for t in tl.get("tools", [])]
    print("     工具：%s" % ", ".join(names))
    ok("工具数 = 8", len(names) == 8, ", ".join(names))
    blob = json.dumps(tl, ensure_ascii=False).lower()
    has_gui = any(k in blob for k in ("screenshot", "截图", "capture", "gui", "png"))
    ok("**tools/list 里没有任何截图 / GUI 工具**", not has_gui,
       "B 结论的先决条件：MCP 层没有这个能力就不能假装有", group="B")
    missing_tool = None if has_gui else "capture_schematic"

    # ---------------- 1) 设计 ----------------
    print("\n[1] 从需求里定六件事（拓扑 / 参数 / 元件数 / 连接 / 探针 / 仿真）")
    F_TEST = 1000.0
    VIN = 1.0
    R = 12000.0
    C = 10e-9
    d = derive_design(R, C, F_TEST, VIN)
    print("     单级极点 f0      = %.1f Hz" % d["f0_per_stage"])
    print("     整体 -3dB        = %.1f Hz（需求 500Hz，偏 %+.2f%%）"
          % (d["f3db_composite"], d["f3db_err_pct"]))
    print("     1kHz 处理论      = gain %.6f / phase %.4f° / amp %.6f V"
          % (d["at_test_freq"]["gain"], d["at_test_freq"]["phase_deg"],
             d["at_test_freq"]["amp"]))
    print("     反例 10k+33nF    = 两级级联后整体 -3dB 只有 %.1f Hz"
          % d["counter_example"]["f3db_if_two_stage"])
    ok("选出来的参数让整体 -3dB 落在 500Hz ±5% 内",
       abs(d["f3db_err_pct"]) <= TOL_FC_PCT,
       "%.1f Hz (%+.2f%%)" % (d["f3db_composite"], d["f3db_err_pct"]))

    # ---------------- 2) 建电路 ----------------
    print("\n[2] 建电路 + 6 个元件")
    r = mcp("create_circuit", {"name": "two_stage_rc_lpf"})
    cid = r.get("circuit_id")
    ok("create_circuit", bool(cid), str(cid))

    r = mcp("add_component", {"circuit_id": cid,
                              "family": "SIGNAL_VOLTAGE_SOURCES",
                              "part": "AC_VOLTAGE", "refdes": "V1",
                              "value": VIN, "parameters": {"frequency": F_TEST}})
    ok("V1 = 1V / 1kHz 正弦", r.get("ok"))

    r = mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                              "part": "RESISTOR_VIRTUAL", "refdes": "R1",
                              "value": R})
    ok("R1 = %.0f Ω" % R, r.get("ok"))

    r = mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                              "part": "RESISTOR_VIRTUAL", "refdes": "R2",
                              "value": R})
    ok("R2 = %.0f Ω（两级同值）" % R, r.get("ok"))

    r = mcp("add_component", {"circuit_id": cid, "family": "CAPACITOR",
                              "part": "CAPACITOR_VIRTUAL", "refdes": "C1",
                              "value": C})
    ok("C1 = %.1f nF" % (C * 1e9), r.get("ok"))

    r = mcp("add_component", {"circuit_id": cid, "family": "CAPACITOR",
                              "part": "CAPACITOR_VIRTUAL", "refdes": "C2",
                              "value": C})
    ok("C2 = %.1f nF（两级同值）" % (C * 1e9), r.get("ok"))

    r = mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                              "part": "GROUND", "refdes": "GND1"})
    ok("GND1", r.get("ok"))

    # ---------------- 3) 连接 ----------------
    print("\n[3] 连接：V1 -> R1 -> n1 -> R2 -> out，两个电容各自到地")
    mcp("connect", {"circuit_id": cid, "pins": [["V1", "1"], ["R1", "1"]],
                    "net": "in"})
    mcp("connect", {"circuit_id": cid, "pins": [["R1", "2"], ["R2", "1"],
                                                ["C1", "1"]], "net": "n1"})
    mcp("connect", {"circuit_id": cid, "pins": [["R2", "2"], ["C2", "1"]],
                    "net": "out"})
    r = mcp("connect", {"circuit_id": cid,
                        "pins": [["V1", "2"], ["C1", "2"], ["C2", "2"],
                                 ["GND1", "1"]], "net": "0"})
    topo = r.get("topology") or {}
    ok("拓扑被判成 ladder（2 串联 + 2 到地）", topo.get("kind") == "ladder",
       str(topo.get("kind")))
    ok("topology.supported=True", topo.get("supported") is True,
       str(topo.get("reason")))

    # ---------------- 4) 探针 ----------------
    print("\n[4] 探针：输入在 in、输出在 out")
    mcp("add_probe", {"circuit_id": cid, "target": "in", "name": "P_in"})
    r = mcp("add_probe", {"circuit_id": cid, "target": "out", "name": "P_out"})
    ok("complete=True（线接完了）",
       (r.get("topology") or {}).get("complete") is True,
       str((r.get("topology") or {}).get("issues")))

    # ---------------- 5) 仿真 ----------------
    print("\n[5] 真机仿真（Multisim 14.3.3）")
    r = mcp("simulate", {"circuit_id": cid, "analysis": "transient",
                         "start": 0.005, "stop": 0.015,
                         "sample_rate": 500000, "timeout": 300})
    ok("simulate 成功", r.get("ok"), str((r.get("error") or {}).get("code") or ""))
    sim_id = r.get("sim_id")
    ms14 = r.get("ms14")
    outs = r.get("outputs") or []
    timing = r.get("timing") or {}
    print("     ms14    : %s" % ms14)
    print("     outputs : %s" % outs)
    print("     timing  : %s" % json.dumps(timing, ensure_ascii=False))
    ok("两个探针都注册上了", len(outs) == 2, str(outs))
    ok("采样点够（500 kHz × 10 ms）", (r.get("n") or 0) >= 4000, str(r.get("n")))

    ms14_fixed = os.path.join(WD, "circuit.ms14")
    if ms14:
        src = ms14 if os.path.isabs(ms14) else os.path.join(ROOT, ms14)
        if os.path.isfile(src):
            shutil.copy2(src, ms14_fixed)
            ok("circuit.ms14 落到固定路径", True,
               "%d B" % os.path.getsize(ms14_fixed))

    # ---------------- 6) measure ----------------
    print("\n[6] measure")
    m = mcp("measure", {"sim_id": sim_id, "what": "all"})
    ok("measure 成功", m.get("ok"))
    th = m.get("theory")
    ok("**MCP 没有二阶理论模型（theory=None）** —— 理论值只能 Agent 自己算",
       th is None, str(th))
    ok("pairing=topology（按拓扑配对，不是按探针顺序）",
       m.get("pairing") == "topology", str(m.get("pairing")))
    print("     实测 gain  = %s" % m.get("gain"))
    print("     实测 phase = %s" % m.get("phase_deg"))
    for pid, ch in (m.get("channels") or {}).items():
        print("     %-6s amp=%.6f  phase=%+.4f°  min=%.6f  max=%.6f"
              % (pid, ch.get("amp") or 0, ch.get("phase_deg") or 0,
                 ch.get("min") or 0, ch.get("max") or 0))

    # ---------------- 7) 波形 ----------------
    print("\n[7] get_waveform")
    r = mcp("get_waveform", {"sim_id": sim_id, "max_points": 8})
    ok("get_waveform 成功", r.get("ok"))
    csv_rel = r.get("artifact")
    probe_of = {p.get("probe_id"): p.get("output")
                for p in (r.get("probes") or [])}
    csv_fixed = os.path.join(WD, "waveform.csv")
    if csv_rel:
        src = csv_rel if os.path.isabs(csv_rel) else os.path.join(ROOT, csv_rel)
        if os.path.isfile(src):
            shutil.copy2(src, csv_fixed)
            ok("waveform.csv 落到固定路径", True,
               "%d B" % os.path.getsize(csv_fixed))

    # ---------------- 8) 独立复算 + 理论比对 ----------------
    print("\n[8] 独立复算（只读 CSV，自己拟合）+ 理论比对")
    rec = recompute(csv_fixed, probe_of, F_TEST) if os.path.isfile(csv_fixed) else None
    verdict = None
    if rec and not rec.get("error"):
        print("     复算 in  : amp=%.6f  phase=%+.4f°  (n=%d, %d 周期)"
              % (rec["in"]["amp"], rec["in"]["phase_deg"],
                 rec["in"]["n"], rec["in"]["cycles"]))
        print("     复算 out : amp=%.6f  phase=%+.4f°"
              % (rec["out"]["amp"], rec["out"]["phase_deg"]))
        print("     复算 gain=%.6f  phase=%+.4f°" % (rec["gain"], rec["phase_deg"]))

        tg = d["at_test_freq"]["gain"]
        tp = d["at_test_freq"]["phase_deg"]
        e_g = (rec["gain"] - tg) / tg * 100.0
        e_p = rec["phase_deg"] - tp
        print("     理论 gain=%.6f  phase=%+.4f°" % (tg, tp))
        print("     误差 gain=%+.4f%%  phase=%+.4f°" % (e_g, e_p))

        # measure 的拟合 vs 我的拟合（两套独立算法应一致）
        d_gm = abs((m.get("gain") or 0) - rec["gain"])
        d_pm = abs((m.get("phase_deg") or 0) - rec["phase_deg"])
        ok("measure 的 gain 与独立复算一致", d_gm < 1e-4, "差 %.2e" % d_gm)
        ok("measure 的 phase 与独立复算一致", d_pm < 1e-3, "差 %.2e°" % d_pm)

        ok("增益相对误差 ≤ %.0f%%" % TOL_GAIN_PCT, abs(e_g) <= TOL_GAIN_PCT,
           "%+.4f%%" % e_g)
        ok("相位误差 ≤ %.0f°" % TOL_PHASE_DEG, abs(e_p) <= TOL_PHASE_DEG,
           "%+.4f°" % e_p)
        ok("输出幅值 = 输入 × 增益（自洽）",
           abs(rec["out"]["amp"] - rec["in"]["amp"] * rec["gain"]) < 1e-9,
           "%.6f vs %.6f" % (rec["out"]["amp"],
                             rec["in"]["amp"] * rec["gain"]))
        ok("输入幅值 = 1V（需求给的）", abs(rec["in"]["amp"] - 1.0) < 0.01,
           "%.6f V" % rec["in"]["amp"])
        verdict = {
            "gain_measured": rec["gain"], "gain_theory": tg, "gain_err_pct": e_g,
            "phase_measured": rec["phase_deg"], "phase_theory": tp,
            "phase_err_deg": e_p,
            "f3db_theory": d["f3db_composite"],
            "f3db_err_pct": d["f3db_err_pct"],
            "tol_gain_pct": TOL_GAIN_PCT, "tol_phase_deg": TOL_PHASE_DEG,
            "tol_fc_pct": TOL_FC_PCT,
            "pass": bool(abs(e_g) <= TOL_GAIN_PCT and abs(e_p) <= TOL_PHASE_DEG
                         and abs(d["f3db_err_pct"]) <= TOL_FC_PCT),
        }
    else:
        ok("CSV 能解析", False, (rec or {}).get("error", "没有 CSV"))

    # ---------------- 9) 终态 ----------------
    print("\n[9] 会话终态")
    r = mcp("get_circuit", {"circuit_id": cid})
    counts = r.get("counts") or {}
    ok("元件数 = 6", counts.get("components") == 6, str(counts))
    ok("网络数 = 4", counts.get("nets") == 4)
    ok("探针数 = 2", counts.get("probes") == 2)

    # ---------------- 10) 截图：B 结论 ----------------
    print("\n[10] 截图（B 结论）")
    print("     8 个工具里没有截图能力 -> Agent 无法在 MCP 链路内截图")
    shot = os.path.join(WD, "screenshot.png")
    shot_ok = os.path.isfile(shot)
    ok("**B：Agent 通过 MCP 拿到真实 Multisim 截图**", False,
       "缺失工具：%s（MCP 无 GUI/截图能力）" % missing_tool, group="B")
    if shot_ok:
        print("     注：%s 存在，但它是验收台在 Agent 链路**之外**"
              "调用库函数得到的" % os.path.relpath(shot, ROOT))
        print("        用来证明「能力存在、只是没包装成工具」，不作为 B 通过的证据")

    # ---------------- 汇总 ----------------
    errs = [c for c in CALLS if not c["ok"]]
    a_fails = [c for c in CHECKS if not c["pass"] and c["group"] == "A"]
    b_fails = [c for c in CHECKS if not c["pass"] and c["group"] == "B"]
    print("\n" + "=" * 80)
    print("工具调用 %d 次，失败 %d 次，总耗时 %.1f s"
          % (len(CALLS), len(errs), sum(c["elapsed"] for c in CALLS)))
    print("A（设计 + 仿真 + 验算）: %s"
          % ("PASS" if not a_fails else "FAIL (%d 项)" % len(a_fails)))
    print("B（+ 真实 GUI 截图，走 MCP）: %s"
          % ("PASS" if not b_fails else "FAIL（缺工具 %s）" % missing_tool))
    if FAILS:
        print("\n未通过项：")
        for f in FAILS:
            print("  - %s" % f)
    print("=" * 80)

    out = {
        "task": TASK,
        "verdict": {
            "A_design_and_simulate": not a_fails,
            "B_design_simulate_and_screenshot_via_mcp": not b_fails,
            "B_blocked_by": None if not b_fails else {
                "missing_tool": missing_tool,
                "mcp_tools": names,
                "note": "MCP 只有 8 个电路工具，没有 GUI 打开 / 视图调整 / 截图能力",
            },
        },
        "design": {
            "decided_by": "agent",
            "topology": "two_stage_rc_lowpass（两级无源 RC 直接级联）",
            "why_no_buffer": "运放不在 MCP 白名单里，只能用无源级联；"
                             "因此必须考虑后级对前级的负载效应",
            "r_ohm": R, "c_f": C,
            "n_components": 6,
            "components": {"V1": "AC_VOLTAGE 1V/1kHz",
                           "R1": R, "R2": R, "C1": C, "C2": C,
                           "GND1": "GROUND"},
            "nets": {"in": ["V1.1", "R1.1"],
                     "n1": ["R1.2", "R2.1", "C1.1"],
                     "out": ["R2.2", "C2.1"],
                     "0": ["V1.2", "C1.2", "C2.2", "GND1.1"]},
            "probes": [{"name": "P_in", "net": "in"},
                       {"name": "P_out", "net": "out"}],
            "simulation": {"analysis": "transient", "start": 0.005,
                           "stop": 0.015, "sample_rate": 500000,
                           "why": "τ=120µs，5ms 后已过 41τ；导出 10 个整周期便于拟合"},
            "derivation": d,
        },
        "artifacts": {
            "ms14": os.path.relpath(ms14_fixed, ROOT)
            if os.path.isfile(ms14_fixed) else None,
            "waveform_csv": os.path.relpath(csv_fixed, ROOT)
            if os.path.isfile(csv_fixed) else None,
            "trace": os.path.relpath(os.path.join(WD, "trace.jsonl"), ROOT),
            "verification": os.path.relpath(os.path.join(WD, "verification.json"), ROOT),
            "screenshot": os.path.relpath(shot, ROOT) if shot_ok else None,
            "screenshot_from_mcp": False,
        },
        "measure": {k: v for k, v in (m or {}).items()
                    if k in ("mode", "pairing", "gain", "phase_deg",
                             "source_amp", "source_freq", "theory", "channels")},
        "recompute": rec,
        "verification": verdict,
        "calls": [{"tool": c["tool"], "ok": c["ok"], "elapsed": c["elapsed"]}
                  for c in CALLS],
        "n_calls": len(CALLS), "n_errors": len(errs),
        "total_s": round(sum(c["elapsed"] for c in CALLS), 1),
        "timing": timing,
        "checks": CHECKS,
        "fails": FAILS,
    }
    with open(os.path.join(WD, "verification.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("报告: %s" % os.path.join(WD, "verification.json"))
    return 0 if not a_fails else 1


if __name__ == "__main__":
    sys.exit(main())
