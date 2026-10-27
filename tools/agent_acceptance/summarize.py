# -*- coding: utf-8 -*-
"""把 trace.jsonl 变成人看的调用序列 + 统计。

报告里"完整调用序列 / 零错误 / 有没有无意义重复调用"这几节全部由它生成，
不靠回忆、不手写。

用法
----
    python tools/agent_acceptance/summarize.py out/agent_v08/p1/trace.jsonl
    python tools/agent_acceptance/summarize.py out/agent_v08/p1/trace.jsonl \
        --md out/agent_v08/p1/calls.md --json out/agent_v08/p1/stats.json
"""
import argparse
import json
import os
import sys


def _short(v, n=48):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n - 1] + "…"


def _key_args(tool, args):
    """每个工具只挑对复现有意义的参数，避免表格被 get_circuit 的快照淹没。"""
    if tool in ("create_circuit",):
        return "name=%s" % args.get("name")
    if tool == "add_component":
        s = "%s %s/%s %s value=%s" % (args.get("refdes") or "(auto)",
                                      args.get("family"), args.get("part"),
                                      "", args.get("value"))
        if args.get("parameters"):
            s += " parameters=%s" % _short(args["parameters"], 40)
        return s.replace("  ", " ")
    if tool == "connect":
        return "pins=%s net=%s" % (_short(args.get("pins"), 60), args.get("net"))
    if tool == "add_probe":
        return "target=%s name=%s" % (args.get("target"), args.get("name"))
    if tool == "simulate":
        return "circuit=%s analysis=%s" % (args.get("circuit_id"),
                                          args.get("analysis"))
    if tool in ("measure", "get_waveform"):
        return "sim=%s probe_id=%s what=%s" % (
            args.get("sim_id"), args.get("probe_id"), args.get("what"))
    return _short(args, 60)


def summarize(recs):
    n_ok = sum(1 for r in recs if r.get("ok"))
    errs = [r for r in recs if not r.get("ok")]
    codes = {}
    for r in errs:
        code = ((r.get("result") or {}).get("error") or {}).get("code") or "UNKNOWN"
        codes[code] = codes.get(code, 0) + 1

    per_tool = {}
    for r in recs:
        per_tool[r["tool"]] = per_tool.get(r["tool"], 0) + 1

    # 连续重复：同工具 + 同参数，连着来两次以上（多半是无意义重试）
    dup = 0
    for a, b in zip(recs, recs[1:]):
        if a["tool"] == b["tool"] and a.get("args") == b.get("args"):
            dup += 1

    total_ms = sum(r.get("elapsed_ms") or 0 for r in recs)
    slow = max(recs, key=lambda r: r.get("elapsed_ms") or 0) if recs else None

    return {
        "calls": len(recs),
        "ok": n_ok,
        "errors": len(errs),
        "error_codes": codes,
        "per_tool": per_tool,
        "consecutive_duplicates": dup,
        "total_elapsed_s": round(total_ms / 1000.0, 1),
        "slowest": ({"tool": slow["tool"], "elapsed_ms": slow["elapsed_ms"]}
                    if slow else None),
        "sequence": [r["tool"] for r in recs],
    }


def to_markdown(recs, stats):
    lines = []
    lines.append("| # | 工具 | 关键参数 | 结果 | 耗时 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in recs:
        res = r.get("result") or {}
        if r.get("ok"):
            tag = "ok"
        else:
            code = (res.get("error") or {}).get("code") or "ERROR"
            tag = "**%s**" % code
        note = ""
        if r.get("injected"):
            note = " ⚠注入"
        lines.append("| %d | `%s` | %s | %s%s | %.0f ms |"
                     % (r["seq"], r["tool"], _key_args(r["tool"], r.get("args") or {}),
                        tag, note, r.get("elapsed_ms") or 0))
    lines.append("")
    lines.append("- 总调用 **%d** 次，成功 **%d**，失败 **%d**"
                 % (stats["calls"], stats["ok"], stats["errors"]))
    lines.append("- 连续重复调用（同工具同参数）：**%d** 次"
                 % stats["consecutive_duplicates"])
    lines.append("- 累计耗时 **%.1f s**（其中 `%s` 占 %.1f s）"
                 % (stats["total_elapsed_s"],
                    (stats["slowest"] or {}).get("tool", "-"),
                    ((stats["slowest"] or {}).get("elapsed_ms") or 0) / 1000.0))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--md", default=None)
    ap.add_argument("--json", default=None)
    o = ap.parse_args(argv)

    recs = []
    with open(o.trace, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    stats = summarize(recs)
    md = to_markdown(recs, stats)

    print(md)
    if o.md:
        with open(o.md, "w", encoding="utf-8") as f:
            f.write(md + "\n")
    if o.json:
        with open(o.json, "w", encoding="utf-8") as f:
            f.write(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
