# -*- coding: utf-8 -*-
"""把 Agent 自己的声明与独立验证结果合成 acceptance.json（规格 §9）。

两者**分开保存**：
  agent_claim        —— Agent 通过 measure 工具拿到、并据此判断的数值
  independent_result —— 从 waveform.csv 原始采样点重算的结果（verify_v092.py）

谁对谁错一目了然，不允许只留一个。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def last_measure(trace_path):
    """trace 里最后一次成功的 measure 调用返回体 —— 这就是 Agent 当时看到的东西。"""
    out = None
    with open(trace_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("tool") == "measure" and r.get("ok"):
                out = {"seq": r["seq"], "ts": r["ts"], "result": r["result"]}
    return out


def build(case_dir):
    case_dir = os.path.abspath(case_dir)
    name = os.path.basename(case_dir)
    trace = os.path.join(case_dir, "trace.jsonl")
    indep_path = os.path.join(case_dir, "independent_result.json")
    indep = json.load(open(indep_path, encoding="utf-8"))

    claim = last_measure(trace)
    claim_view = None
    if claim:
        r = claim["result"]
        claim_view = {
            "tool": "measure",
            "seq": claim["seq"],
            "mode": r.get("mode"),
            "pairing": r.get("pairing"),
            "gain": r.get("gain"),
            "phase_deg": r.get("phase_deg"),
            "channels": {k: {kk: v.get(kk) for kk in ("amp", "min", "max", "mean")}
                         for k, v in (r.get("channels") or {}).items()},
            "theory": r.get("theory"),
        }

    files = {}
    for fn in ("requirement.txt", "circuit.ms14", "waveform.csv",
               "01_schematic.png", "02_simulation.png", "acceptance_spec.json"):
        p = os.path.join(case_dir, fn)
        if os.path.isfile(p):
            files[fn] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}

    iterations = []
    for sub in sorted(os.listdir(case_dir)):
        d = os.path.join(case_dir, sub)
        if sub.startswith("iteration_") and os.path.isdir(d):
            sim = os.path.join(d, "sim_record.json")
            g = None
            if os.path.isfile(sim):
                rec = json.load(open(sim, encoding="utf-8"))
                g = rec.get("gain")
            iterations.append({"dir": sub,
                               "circuit_sha256": sha256(os.path.join(d, "circuit.ms14"))
                               if os.path.isfile(os.path.join(d, "circuit.ms14")) else None,
                               "agent_reported_gain": g})

    out = {
        "case": name,
        "requirement": open(os.path.join(case_dir, "requirement.txt"),
                            encoding="utf-8").read().strip(),
        "agent_claim": claim_view,
        "independent_result": indep,
        "agreement": None,
        "iterations": iterations,
        "files": files,
        "verdict": "PASS" if indep.get("pass") else "FAIL",
    }

    # 两边都给了 gain 就对照一下，差得太多要写出来
    if claim_view and claim_view.get("gain") and indep["measured"].get("gain"):
        a = claim_view["gain"]
        b = indep["measured"]["gain"]
        out["agreement"] = {
            "agent_gain": round(a, 6),
            "independent_gain": round(b, 6),
            "abs_diff": round(abs(a - b), 6),
            "rel_diff_pct": round(abs(a - b) / b * 100, 4),
        }

    with open(os.path.join(case_dir, "acceptance.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    dirs = sys.argv[1:] or [
        os.path.join(ROOT, "out", "agent_v092", c)
        for c in ("case_a_rc", "case_b_rectifier", "case_c_iterative")
    ]
    for d in dirs:
        o = build(d)
        print("%-18s %s  agent_gain=%s  indep_gain=%s  agree=%s"
              % (o["case"], o["verdict"],
                 (o["agent_claim"] or {}).get("gain"),
                 o["independent_result"]["measured"].get("gain"),
                 o["agreement"]))
