# -*- coding: utf-8 -*-
"""v0.9 Agent 验收：DIODE / 1N4007G 从 MCP 到真机仿真的完整闭环。

**这个脚本不 import 任何项目模块。** 它只做两件事：
  1. 用 `agent_cli.py` 起独立进程调 MCP 工具（Agent 唯一的入口）
  2. 拿工具返回的 JSON / CSV 自己算一遍（独立复算，不信项目自己的 theory）

验收链（缺一环就不算通）：
    Agent -> MCP add_component(DIODE/1N4007G) -> Circuit IR -> layout
          -> msbuild donor 克隆 -> connect -> .ms14 -> Multisim 14.3.3
          -> 真实仿真 -> measure -> 电气验证

跑法：
    runtime\\py32\\python.exe tools/agent_acceptance/run_diode.py
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
WD = os.path.join(ROOT, "out", "agent_v09", "diode")

# 电路参数（写在这里，理论值也用这些算）
VM = 5.0          # 源峰值 V
FREQ = 50.0       # Hz
RS = 1000.0       # 负载 Ω

CALLS = []
FAILS = []


def ok(name, cond, detail=""):
    if cond:
        print("  %-52s OK   %s" % (name, detail))
    else:
        FAILS.append(name)
        print("  %-52s FAIL %s" % (name, detail))
    return cond


def mcp(tool, args=None):
    """一次工具调用 = 一个独立进程（v0.8 的设计，Agent 拿不到进程内状态）。"""
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
        extra = "%s | %s" % (e.get("code"), (e.get("message") or "")[:90])
    print("  [%5.1fs] %-14s %s  %s" % (dt, tool, tag, extra))
    return r


def tools_list():
    p = subprocess.run([PY, CLI, "--workdir", WD, "tools"],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return json.loads(p.stdout)


# ---------------------------------------------------------------------------
# 独立复算：只读 CSV 和 IR JSON，不碰项目代码
# ---------------------------------------------------------------------------
def recompute(csv_path, probe_of, vm, freq, rs):
    """从波形 CSV 自己算整流指标（不 import 项目代码）。

    这里刻意**不用点值理论**。第一版用 `Vdc = Vm/π - Vf/2` 去卡实测，差了 2.0%；
    查波形才发现恒定压降假设只在深导通区成立（开启点远低于饱和压降）。
    所以改成两件事：

      1. 直接验证物理行为：深导通区压降是不是常数、反偏区是不是真的截止；
      2. 用区间校验：Vdc ∈ (Vm/π - Vf/2, Vm/π)，导通占比 ∈ (恒定压降模型, 0.5)。
         实测必须落在区间内，并给出它偏向哪一端。
    """
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head = rows[0][1:]
    cols = {h: [] for h in head}
    t = []
    for r in rows[1:]:
        if not r:
            continue
        t.append(float(r[0]))
        for i, h in enumerate(head, 1):
            cols[h].append(float(r[i]))

    out_col = probe_of.get("P_out")
    in_col = probe_of.get("P_in")
    if out_col not in cols:
        return {"error": "CSV 里没有输出通道 %r（实际列：%s）" % (out_col, head)}
    if in_col not in cols:
        return {"error": "CSV 里没有输入通道 %r（实际列：%s）" % (in_col, head)}

    v = cols[out_col]
    vi = cols[in_col]
    v_peak, v_min = max(v), min(v)
    v_dc = sum(v) / len(v)
    v_in_peak = max(vi)
    vf_peak = v_in_peak - v_peak

    # 深导通区逐点压降
    seg = [a - b for a, b in zip(vi, v) if a >= 0.8 * v_in_peak]
    mean = sum(seg) / len(seg)
    var = sum((x - mean) ** 2 for x in seg) / len(seg)

    # 反偏区：输出应被完全挡住
    off = [b for a, b in zip(vi, v) if a <= -0.1 * v_in_peak]
    rev_max = max(abs(x) for x in off) if off else 0.0

    # 区间
    v_dc_lo = v_in_peak / math.pi - vf_peak / 2.0
    v_dc_hi = v_in_peak / math.pi
    thr = 0.01 * v_peak
    frac_meas = sum(1 for x in v if x > thr) / float(len(v))
    arg = min(0.999999, max(0.0, (vf_peak + thr) / v_in_peak))
    frac_lo = (math.pi - 2.0 * math.asin(arg)) / (2.0 * math.pi)

    return {
        "n": len(v), "t_range": [t[0], t[-1]],
        "v_in_peak": v_in_peak, "v_out_peak": v_peak, "v_out_min": v_min,
        "v_out_mean": v_dc, "vf_peak": vf_peak,
        "vf_deep_on": {"n": len(seg), "mean": mean, "std": math.sqrt(var),
                       "min": min(seg), "max": max(seg)},
        "reverse_block_max": rev_max,
        "v_dc_lo": v_dc_lo, "v_dc_hi": v_dc_hi,
        "v_dc_inside": bool(v_dc_lo <= v_dc <= v_dc_hi),
        "v_dc_pos": (v_dc - v_dc_lo) / (v_dc_hi - v_dc_lo),
        "conduction_meas": frac_meas,
        "conduction_lo": frac_lo, "conduction_hi": 0.5,
        "conduction_inside": bool(frac_lo <= frac_meas <= 0.5),
        "conduction_pos": (frac_meas - frac_lo) / (0.5 - frac_lo),
    }


def main():
    os.makedirs(WD, exist_ok=True)
    trace = os.path.join(WD, "trace.jsonl")
    if os.path.isfile(trace):
        os.remove(trace)                       # 每次验收从干净的 trace 开始

    print("=" * 78)
    print("v0.9 Agent 验收：DIODE / 1N4007G 半波整流闭环")
    print("workdir: %s" % WD)
    print("=" * 78)

    # ---------- 0) tools/list ----------
    print("\n[0] Agent 只能看到 tools/list")
    tl = tools_list()
    names = [t["name"] for t in tl.get("tools", [])]
    ok("8 个工具都在", len(names) == 8, ", ".join(names))
    ac = next((t for t in tl["tools"] if t["name"] == "add_component"), {})
    desc = ac.get("description") or ""
    ok("schema 里写明了 DIODE/1N4007G", "DIODE, part=1N4007G" in desc)
    ok("schema 里写明了引脚 A/K", "'A' 'K'" in desc)
    ok("schema 里写明了只支持半波整流这一种拓扑",
       "半波整流" in desc and "LAYOUT_UNSUPPORTED" in desc)

    # ---------- 1) 建电路 ----------
    print("\n[1] 建电路 + 加元件（关键一步是 DIODE）")
    r = mcp("create_circuit", {"name": "halfwave_1n4007g"})
    cid = r.get("circuit_id")
    ok("create_circuit", bool(cid), str(cid))

    r = mcp("add_component", {"circuit_id": cid,
                              "family": "SIGNAL_VOLTAGE_SOURCES",
                              "part": "AC_VOLTAGE", "refdes": "V1",
                              "value": VM, "parameters": {"frequency": FREQ}})
    ok("加正弦源 V1 (5V/50Hz)", r.get("ok"))

    r = mcp("add_component", {"circuit_id": cid, "family": "DIODE",
                              "part": "1N4007G", "refdes": "D1"})
    ok("加二极管 D1 —— **不再报 UNKNOWN_COMPONENT_TYPE**", r.get("ok"),
       str((r.get("error") or {}).get("code") or ""))
    comp = r.get("component") or {}
    ok("D1 的 pins 是 A/K", comp.get("pins") == ["A", "K"], str(comp.get("pins")))
    ok("D1 的 value 是 None（型号决定一切）", comp.get("value") is None)

    mcp("add_component", {"circuit_id": cid, "family": "RESISTOR",
                          "part": "RESISTOR_VIRTUAL", "refdes": "R1",
                          "value": RS})
    mcp("add_component", {"circuit_id": cid, "family": "POWER_SOURCES",
                          "part": "GROUND", "refdes": "GND1"})

    # ---------- 2) 接线 ----------
    print("\n[2] 接线 V1 -> D1 -> R1 -> GND")
    mcp("connect", {"circuit_id": cid, "pins": [["V1", "+"], ["D1", "A"]],
                    "net": "in"})
    mcp("connect", {"circuit_id": cid, "pins": [["D1", "K"], ["R1", "1"]],
                    "net": "out"})
    r = mcp("connect", {"circuit_id": cid,
                        "pins": [["V1", "-"], ["R1", "2"], ["GND1", "1"]],
                        "net": "0"})
    topo = r.get("topology") or {}
    ok("拓扑被判成 halfwave_rectifier", topo.get("kind") == "halfwave_rectifier",
       str(topo.get("kind")))
    ok("topology.supported=True", topo.get("supported") is True,
       str(topo.get("reason")))

    print("\n[3] 加探针（输入 / 输出各一个）")
    mcp("add_probe", {"circuit_id": cid, "target": "in", "name": "P_in"})
    r = mcp("add_probe", {"circuit_id": cid, "target": "out", "name": "P_out"})
    ok("complete=True（线接完了）",
       (r.get("topology") or {}).get("complete") is True,
       str((r.get("topology") or {}).get("issues")))

    # ---------- 4) 仿真 ----------
    print("\n[4] 真机仿真（Multisim 14.3.3）")
    r = mcp("simulate", {"circuit_id": cid, "analysis": "transient",
                         "start": 0.0, "stop": 0.1, "sample_rate": 100000,
                         "timeout": 300})
    ok("simulate 成功", r.get("ok"), str((r.get("error") or {}).get("code") or ""))
    sim_id = r.get("sim_id")
    ms14 = r.get("ms14")
    outs = r.get("outputs") or []
    timing = r.get("timing") or {}
    print("     ms14   : %s" % ms14)
    print("     outputs: %s" % outs)
    print("     timing : %s" % json.dumps(timing, ensure_ascii=False))
    ok("**两个探针都注册上了**（上次只注册了一个）", len(outs) == 2, str(outs))
    ok("采样点数够（5 个周期 @ 100kHz）", (r.get("n") or 0) >= 5000, str(r.get("n")))

    # 把 .ms14 复制到固定位置（会话目录会被 gitignore 掉）
    ms14_fixed = os.path.join(WD, "halfwave_1n4007g.ms14")
    if ms14:
        src = ms14 if os.path.isabs(ms14) else os.path.join(ROOT, ms14)
        if os.path.isfile(src):
            shutil.copy2(src, ms14_fixed)
            ok(".ms14 落到固定路径", True, ms14_fixed)

    # ---------- 5) 读数 ----------
    print("\n[5] measure")
    r = mcp("measure", {"sim_id": sim_id, "what": "all"})
    meas = r
    ok("measure 成功", r.get("ok"))
    ok("mode=rectifier（没有套正弦拟合）", r.get("mode") == "rectifier",
       str(r.get("mode")))
    ok("没有给出 gain（整流电路没有增益这个概念）", "gain" not in r)
    th = r.get("theory") or {}
    br = r.get("bracket") or {}
    print("     实测 v_out_peak = %.4f V" % (r.get("v_out_peak") or 0))
    print("     实测 v_out_min  = %.5f V" % (r.get("v_out_min") or 0))
    print("     实测 v_out_mean = %.4f V" % (r.get("v_out_mean") or 0))
    print("     实测 vf_peak    = %.4f V" % (r.get("vf_peak") or 0))
    print("     实测 vf_deep_on = %s" % json.dumps(r.get("vf_deep_on"),
                                                  ensure_ascii=False))
    print("     实测导通占比    = %.4f" % (r.get("conduction_frac") or 0))
    print("     bracket         = %s" % json.dumps(br, ensure_ascii=False))
    ok("bracket 里直流分量判在区间内", (br.get("v_dc") or {}).get("inside") is True,
       json.dumps(br.get("v_dc"), ensure_ascii=False))
    ok("bracket 里导通占比判在区间内",
       (br.get("conduction_frac") or {}).get("inside") is True,
       json.dumps(br.get("conduction_frac"), ensure_ascii=False))
    ok("vf_deep_on 报了压降的均值和标准差", bool(r.get("vf_deep_on")),
       str(th.get("kind")))

    # ---------- 6) 波形 ----------
    print("\n[6] get_waveform")
    r = mcp("get_waveform", {"sim_id": sim_id, "max_points": 8})
    ok("get_waveform 成功", r.get("ok"))
    csv_rel = r.get("artifact")
    ok("有 CSV 产物", bool(csv_rel), str(csv_rel))

    # 波形也复制到固定位置：会话目录被 gitignore，文档里点不开
    csv_fixed = os.path.join(WD, "halfwave_1n4007g.csv")
    if csv_rel:
        src = csv_rel if os.path.isabs(csv_rel) else os.path.join(ROOT, csv_rel)
        if os.path.isfile(src):
            shutil.copy2(src, csv_fixed)
            ok("波形落到固定路径", True, csv_fixed)

    # ---------- 7) 独立复算 ----------
    print("\n[7] 独立复算（只读 CSV，不 import 项目模块）")
    rec = None
    if csv_rel:
        probe_of = {}
        for p in (r.get("probes") or []):
            probe_of[p.get("probe_id")] = p.get("output")
        csv_path = (csv_fixed if os.path.isfile(csv_fixed)
                    else (csv_rel if os.path.isabs(csv_rel)
                          else os.path.join(ROOT, csv_rel)))
        rec = recompute(csv_path, probe_of, VM, FREQ, RS)
        if rec.get("error"):
            ok("CSV 能解析", False, rec["error"])
        else:
            d = rec["vf_deep_on"]
            print("     复算: v_out_peak=%.4f  v_out_min=%.5f  v_out_mean=%.4f"
                  % (rec["v_out_peak"], rec["v_out_min"], rec["v_out_mean"]))
            print("     复算: 深导通压降 mean=%.4f std=%.4f (n=%d)"
                  % (d["mean"], d["std"], d["n"]))
            print("     复算: Vdc ∈ (%.4f, %.4f)  实测 %.4f  pos=%.3f"
                  % (rec["v_dc_lo"], rec["v_dc_hi"], rec["v_out_mean"],
                     rec["v_dc_pos"]))
            print("     复算: 导通占比 ∈ (%.4f, %.4f)  实测 %.4f  pos=%.3f"
                  % (rec["conduction_lo"], rec["conduction_hi"],
                     rec["conduction_meas"], rec["conduction_pos"]))

            ok("深导通区压降落在 1N4007 合理区间 (0.5~0.8 V)",
               0.5 <= d["mean"] <= 0.8, "mean=%.4f V" % d["mean"])
            ok("深导通区压降近似常数（std < 20 mV）",
               d["std"] < 0.02, "std=%.4f V" % d["std"])
            ok("反偏半周被挡住（|v_out| < 5 mV）",
               rec["reverse_block_max"] < 0.005,
               "max=%.5f V" % rec["reverse_block_max"])
            ok("直流分量落在 [恒定压降, 理想二极管] 区间内",
               rec["v_dc_inside"],
               "%.4f ∈ (%.4f, %.4f)" % (rec["v_out_mean"], rec["v_dc_lo"],
                                        rec["v_dc_hi"]))
            ok("直流分量偏向恒定压降端（pos < 0.35）",
               0 <= rec["v_dc_pos"] < 0.35, "pos=%.3f" % rec["v_dc_pos"])
            ok("导通占比落在 [恒定压降, 50%] 区间内",
               rec["conduction_inside"],
               "%.4f ∈ (%.4f, 0.5)" % (rec["conduction_meas"],
                                       rec["conduction_lo"]))
            ok("导通占比偏向理想端（开启点远低于饱和压降，pos > 0.5）",
               rec["conduction_pos"] > 0.5, "pos=%.3f" % rec["conduction_pos"])
            # 项目自己算的 vs 独立复算：两边必须一致
            if meas.get("v_out_mean") is not None:
                dd = abs(meas["v_out_mean"] - rec["v_out_mean"])
                ok("measure 的直流分量与独立复算一致", dd < 1e-6, "差 %.2e" % dd)

    # ---------- 8) 终态 ----------
    print("\n[8] 会话终态")
    r = mcp("get_circuit", {"circuit_id": cid})
    ok("元件数 = 4", (r.get("counts") or {}).get("components") == 4,
       str(r.get("counts")))
    ok("网络数 = 3", (r.get("counts") or {}).get("nets") == 3)
    ok("探针数 = 2", (r.get("counts") or {}).get("probes") == 2)

    # ---------- 汇总 ----------
    errs = [c for c in CALLS if not c["ok"]]
    print("\n" + "=" * 78)
    print("工具调用 %d 次，失败 %d 次，总耗时 %.1f s"
          % (len(CALLS), len(errs), sum(c["elapsed"] for c in CALLS)))
    print("断言失败 %d 项" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  - %s" % f)
    print("=" * 78)

    summary = {
        "circuit_id": cid, "sim_id": sim_id,
        "ms14": os.path.relpath(ms14_fixed, ROOT)
        if os.path.isfile(ms14_fixed) else None,
        "csv": os.path.relpath(csv_fixed, ROOT)
        if os.path.isfile(csv_fixed) else None,
        "csv_session_copy": csv_rel,
        "calls": [{"tool": c["tool"], "ok": c["ok"], "elapsed": c["elapsed"]}
                  for c in CALLS],
        "n_calls": len(CALLS), "n_errors": len(errs),
        "total_s": round(sum(c["elapsed"] for c in CALLS), 1),
        "timing": timing,
        "measure": {k: v for k, v in (meas or {}).items() if k in
                    ("mode", "v_out_peak", "v_out_min", "v_out_mean",
                     "vf_peak", "vf_deep_on", "reverse_block_max",
                     "conduction_frac", "theory", "bracket")},
        "recompute": rec,
        "fails": FAILS,
        "pass": not FAILS,
    }
    with open(os.path.join(WD, "acceptance.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("报告: %s" % os.path.join(WD, "acceptance.json"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
