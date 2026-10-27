# -*- coding: utf-8 -*-
"""把 v0.8.0 基线 和 14.3.3 复测 的结果并排比。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def load_trace(p):
    out = []
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                out.append(json.loads(ln))
    return out


def pick(tr, tool, nth=0):
    hits = [r for r in tr if r["tool"] == tool]
    return hits[nth] if len(hits) > nth else None


def summarize(tag, trace_path):
    tr = load_trace(trace_path)
    if not tr:
        print("%-10s 没有 trace: %s" % (tag, trace_path))
        return None
    sim = pick(tr, "simulate")
    mea = pick(tr, "measure")
    d = {"tag": tag, "calls": len(tr),
         "errors": sum(1 for r in tr if r.get("is_error")),
         "total_ms": round(sum(r.get("elapsed_ms", 0) for r in tr), 1)}
    if sim:
        d["sim_ok"] = sim["result"].get("status")
        d["n"] = sim["result"].get("n")
        d["compile_s"] = sim["result"].get("timing", {}).get("compile_s")
        d["run_s"] = sim["result"].get("timing", {}).get("run_s")
        d["total_s"] = sim["result"].get("timing", {}).get("total_s")
    if mea:
        ch = mea["result"].get("channels") or {}
        d["pairing"] = mea["result"].get("pairing")
        d["channels"] = {k: {"amp": v.get("amp"), "phase": v.get("phase_deg"),
                             "net": v.get("net")} for k, v in ch.items()}
        d["gain"] = mea["result"].get("gain") or mea["result"].get("transfer")
    return d


base = summarize("v0.8.0", os.path.join(ROOT, "out", "agent_v08", "p1", "trace.jsonl"))
new = summarize("14.3.3", os.path.join(ROOT, "out", "agent_v083", "p1", "trace.jsonl"))

for d in (base, new):
    print("\n=== %s ===" % d["tag"])
    for k, v in d.items():
        if k == "tag":
            continue
        print("  %-11s %s" % (k, json.dumps(v, ensure_ascii=False)[:300]))

print("\n=== 理论值 ===")
import math
R, C, f = 1000.0, 3.3e-7, 1000.0
fc = 1.0 / (2 * math.pi * R * C)
H = 1.0 / math.sqrt(1 + (f / fc) ** 2)
print("  fc = %.2f Hz" % fc)
print("  |H(1kHz)| = %.6f   (%.2f dB)" % (H, 20 * math.log10(H)))
print("  相位 = %.2f deg" % (-math.degrees(math.atan(f / fc))))
if new and new.get("channels"):
    a_out = new["channels"].get("P_out", {}).get("amp")
    a_in = new["channels"].get("P_in", {}).get("amp")
    if a_out and a_in:
        print("  实测 gain = %.6f  (误差 %.3f%%)" % (a_out / a_in, abs(a_out / a_in - H) / H * 100))
