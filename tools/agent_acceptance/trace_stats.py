# -*- coding: utf-8 -*-
"""从 trace.jsonl 统计调用情况（规格 §14 要的那几个数字）。

只用 trace 本身，不猜：每次 agent_cli 调用都会追加一行，含 ok / is_error / elapsed_ms。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime


def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def stats(trace_path):
    recs = load(trace_path)
    if not recs:
        return {"trace": trace_path, "total_tool_calls": 0}
    t0 = datetime.fromisoformat(recs[0]["ts"])
    t1 = datetime.fromisoformat(recs[-1]["ts"])
    by_tool = {}
    for r in recs:
        by_tool.setdefault(r["tool"], {"n": 0, "ok": 0, "fail": 0})
        by_tool[r["tool"]]["n"] += 1
        if r.get("ok"):
            by_tool[r["tool"]]["ok"] += 1
        else:
            by_tool[r["tool"]]["fail"] += 1
    circuits = {r["result"].get("circuit_id") for r in recs
                if r["tool"] == "create_circuit" and isinstance(r.get("result"), dict)}
    sims = [r["result"].get("sim_id") for r in recs
            if r["tool"] == "simulate" and isinstance(r.get("result"), dict)
            and r["result"].get("ok")]
    return {
        "trace": trace_path,
        "total_tool_calls": len(recs),
        "successful_tool_calls": sum(1 for r in recs if r.get("ok")),
        "failed_tool_calls": sum(1 for r in recs if not r.get("ok")),
        "error_responses": sum(1 for r in recs if r.get("is_error")),
        "simulation_count": len([s for s in sims if s]),
        "circuit_count": len([c for c in circuits if c]),
        "tool_breakdown": by_tool,
        "first_call": recs[0]["ts"],
        "last_call": recs[-1]["ts"],
        "wall_time_s": round((t1 - t0).total_seconds(), 1),
        "total_tool_elapsed_ms": round(sum(r.get("elapsed_ms") or 0 for r in recs), 1),
        "error_codes": sorted({(r.get("result") or {}).get("error", {}).get("code")
                               for r in recs
                               if isinstance(r.get("result"), dict)
                               and isinstance(r["result"].get("error"), dict)
                               and r["result"]["error"].get("code")}),
    }


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(stats(p), ensure_ascii=False, indent=2))
