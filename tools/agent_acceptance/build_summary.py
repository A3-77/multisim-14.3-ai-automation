# -*- coding: utf-8 -*-
"""合成 out/agent_v092/summary.json（规格 §14 / §15）。

只读已有产物，不重新仿真：
  acceptance.json        -> 判定 + agent_claim / independent_result
  trace.jsonl            -> 调用统计、设计动作（元件清单）
  independent_result.json-> 独立复算数值
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "agent_acceptance"))
import trace_stats as T  # noqa: E402

CASES = [
    ("case_a_rc", "A", "低通滤波：fc≈500Hz，1kHz 增益≈0.5", "Level 3"),
    ("case_b_rectifier", "B", "5V/50Hz -> 只保留正半周的脉动直流", "Level 3"),
    ("case_c_iterative", "C", "无源滤波：1kHz 增益 0.70±5%（含迭代）", "Level 4"),
]


def design_of(trace_path):
    """从 trace 里读 Agent 实际加了哪些元件、参数是多少 —— 不猜。"""
    comps = []
    for r in T.load(trace_path):
        if r.get("tool") == "add_component" and r.get("ok"):
            res = r.get("result") or {}
            comps.append({
                "refdes": res.get("refdes") or res.get("designator"),
                "type": (r.get("args") or {}).get("type") or res.get("type"),
                "parameters": (r.get("args") or {}).get("parameters"),
                "frequency": (r.get("args") or {}).get("frequency"),
            })
    return comps


def main():
    rows, stats = [], {}
    for name, tag, req, level in CASES:
        d = os.path.join(ROOT, "out", "agent_v092", name)
        acc = json.load(open(os.path.join(d, "acceptance.json"), encoding="utf-8"))
        st = T.stats(os.path.join(d, "trace.jsonl"))
        indep = acc["independent_result"]["measured"]
        claim = acc["agent_claim"] or {}
        n_iter = len(acc.get("iterations") or [])
        rows.append({
            "case": tag,
            "dir": name,
            "requirement": req,
            "design": design_of(os.path.join(d, "trace.jsonl")),
            "agent_claim": {
                "gain": claim.get("gain"),
                "phase_deg": claim.get("phase_deg"),
                "mode": claim.get("mode"),
            },
            "independent_result": {
                "gain": indep.get("gain"),
                "phase_deg": indep.get("phase_deg"),
                "input_freq_hz": indep.get("input_freq_hz"),
                "input_peak_v": indep.get("input_peak_v"),
                "cutoff_hz_derived": indep.get("cutoff_hz_derived"),
                "neg_ratio": indep.get("neg_ratio"),
                "pos_ratio": indep.get("pos_ratio"),
            },
            "agreement": acc.get("agreement"),
            "simulation_count": st["simulation_count"],
            "iteration_count": n_iter,
            "tool_calls": st["total_tool_calls"],
            "failed_tool_calls": st["failed_tool_calls"],
            "wall_time_s": st["wall_time_s"],
            "level": level,
            "verdict": acc["verdict"],
        })
        stats[name] = {k: st[k] for k in (
            "total_tool_calls", "successful_tool_calls", "failed_tool_calls",
            "simulation_count", "circuit_count", "wall_time_s", "tool_breakdown",
            "error_codes", "first_call", "last_call")}

    total = {
        "cases": len(rows),
        "passed": sum(1 for r in rows if r["verdict"] == "PASS"),
        "failed": sum(1 for r in rows if r["verdict"] != "PASS"),
        "total_tool_calls": sum(r["tool_calls"] for r in rows),
        "total_failed_tool_calls": sum(r["failed_tool_calls"] for r in rows),
        "simulation_count": sum(r["simulation_count"] for r in rows),
        "iteration_count": sum(r["iteration_count"] for r in rows),
        "wall_time_s": round(sum(r["wall_time_s"] for r in rows), 1),
        "max_level": max((r["level"] for r in rows), default=None),
    }

    out = {
        "version": "v0.9.2",
        "baseline_commit": "25f0cc6",
        "baseline_tag": "v0.9.1",
        "goal": "验证真 LLM Agent 能否仅凭自然语言工程需求，自主判断电路类型、"
                "选拓扑、选元件、算参数、调 MCP 建电路、跑真实 Multisim 仿真、"
                "读结果判定，并在不满足时自行修正重跑",
        "tool_surface": ["create_circuit", "add_component", "connect", "add_probe",
                         "get_circuit", "simulate", "measure", "get_waveform"],
        "component_library": ["AC_VOLTAGE", "RESISTOR", "CAPACITOR",
                              "DIODE/1N4007G", "GROUND"],
        "table_columns": ["case", "requirement", "design", "agent_claim",
                          "independent_result", "agreement", "simulation_count",
                          "verdict"],
        "rows": rows,
        "stats": stats,
        "totals": total,
        "levels": {
            "1": "能把电路建起来（工具调通）",
            "2": "能跑通真实仿真并读回波形",
            "3": "自主选拓扑/算参数，一次设计即满足指标",
            "4": "设计失败后能自行归因、改参数、重跑并收敛",
        },
        "evidence": {
            "schematic": "每个 Case 的 01_schematic.png（真实 Multisim 窗口截图）",
            "simulation": "每个 Case 的 02_simulation.png（图示仪窗口截图）",
            "capture_method": "PrintWindow(PW_RENDERFULLCONTENT) + GetDIBits -> zlib PNG",
            "capture_entry": "tools/screenshot.py: capture_schematic / capture_simulation",
            "provenance": "capture_provenance.json（PNG 与 .ms14 / waveform.csv 的 SHA-256 关联）",
        },
        "methodology_caveat": (
            "三个 Case 的拓扑选择、元件选择、参数计算、失败归因与修正，全部由 LLM 在"
            "对话中做出，逐条经 tools/agent_acceptance/agent_cli.py 以 stdio JSON-RPC "
            "调用 MCP 完成；trace.jsonl 记录的是真实工具调用序列，harness 里没有任何"
            "Case 分支、没有写死拓扑或 R/C 数值。但执行层面是逐条发命令、而不是单个"
            "进程内的自主循环——这一点必须如实标注。"),
    }
    p = os.path.join(ROOT, "out", "agent_v092", "summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(total, ensure_ascii=False, indent=2))
    print("->", p)


if __name__ == "__main__":
    main()
