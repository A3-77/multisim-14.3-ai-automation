# -*- coding: utf-8 -*-
"""Agent CLI —— 外部 LLM Agent 唯一的入口。

Agent 只被允许做三件事：

    agent_cli.py tools                      # 看 tools/list（schema + description）
    agent_cli.py schema <tool>              # 看单个工具的 schema
    agent_cli.py call <tool> '<json args>'  # 调一个工具，拿返回值

stdout 永远是**一个 JSON 对象**（工具返回的 payload），方便 Agent 直接读；
过程信息（耗时、trace 路径）走 stderr。

每次调用都会往 `<workdir>/trace.jsonl` 追加一条完整记录：

    {"seq":1,"ts":"...","tool":"create_circuit","args":{...},
     "ok":true,"is_error":false,"elapsed_ms":123,"result":{...}}

这就是"完整 tool call / tool result 日志"——报告里的调用序列、错误恢复
分析、无意义重复调用统计全部从它生成，不靠回忆。

故障注入（--profile）
---------------------
`--profile case1-missing-frequency` 会在**第一次** `add_component` 一个
AC_VOLTAGE 时，把 `frequency` / `parameters` 从参数里摘掉，让 server 真的
返回 MISSING_PARAMETER。注入只发生一次，而且会在 trace 里写 `"injected": "..."`。
这样做是为了测"缺参数时 Agent 能不能只靠 error.hint + context.field 恢复"，
而不是在任务描述里直接告诉它"第一次别传 frequency"。

用法
----
    python tools/agent_acceptance/agent_cli.py --workdir out/agent_v08/p1 tools
    python tools/agent_acceptance/agent_cli.py --workdir out/agent_v08/p1 \
        call create_circuit '{"name":"rc_1st"}'
    python tools/agent_acceptance/agent_cli.py --workdir out/agent_v08/p1 \
        call add_component @args.json          # 参数太长时写成文件
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from mcp_stdio import McpServer, McpError   # noqa: E402


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------
def _read_seq(path):
    if not os.path.isfile(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _append_trace(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 故障注入
# ---------------------------------------------------------------------------
def _inject(profile, tool, args, state):
    """返回 (args, note)。state 是跨调用持久的（存在 workdir 里）。

    profile 是一个**不透明代号**（p3a）—— 不写 "missing-frequency" 这种会
    泄题的字符串，Agent 就算看见命令里那一段也读不出注入内容。
    """
    if not profile:
        return args, None
    flag = os.path.join(state["workdir"], ".inject-%s.done" % profile)
    if os.path.isfile(flag):
        return args, None
    if profile in ("p3a", "case1-missing-frequency") and tool == "add_component":
        if str(args.get("part") or "") == "AC_VOLTAGE":
            args = dict(args)
            dropped = []
            if "frequency" in args:
                args.pop("frequency")
                dropped.append("frequency")
            if "parameters" in args:
                args.pop("parameters")
                dropped.append("parameters")
            with open(flag, "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%dT%H:%M:%S"))
            return args, ("dropped %s from the first AC_VOLTAGE add_component"
                          % " / ".join(dropped or ["(nothing)"]))
    return args, None


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def _load_args(text):
    if text == "-":
        return json.loads(sys.stdin.read())
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as f:
            return json.load(f)
    return json.loads(text)


def _payload(result):
    """MCP tools/call 的 result -> Agent 真正要看的那份 JSON。"""
    if not isinstance(result, dict):
        return result
    sc = result.get("structuredContent")
    if isinstance(sc, dict):
        return sc
    content = result.get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                return json.loads(item.get("text"))
            except ValueError:
                return {"text": item.get("text")}
    return result


def cmd_tools(srv, opts):
    tools = srv.list_tools()
    return {"ok": True, "count": len(tools), "tools": tools}


def cmd_schema(srv, opts):
    tools = srv.list_tools()
    if not opts.name:
        return {"ok": True, "names": [t.get("name") for t in tools]}
    for t in tools:
        if t.get("name") == opts.name:
            return {"ok": True, "tool": t}
    return {"ok": False,
            "error": {"code": "UNKNOWN_TOOL", "message": "没有这个工具：%r" % opts.name,
                      "hint": "可用：%s" % ", ".join(t.get("name") for t in tools)}}


def cmd_call(srv, opts):
    args = _load_args(opts.args_json)
    if not isinstance(args, dict):
        return {"ok": False,
                "error": {"code": "BAD_ARGUMENT",
                          "message": "参数必须是一个 JSON 对象"}}
    trace = os.path.join(opts.workdir, "trace.jsonl")
    state = {"workdir": opts.workdir}
    sent, note = _inject(opts.profile, opts.name, args, state)

    seq = _read_seq(trace) + 1
    t0 = time.time()
    try:
        raw = srv.call_tool(opts.name, sent)
        payload = _payload(raw)
        is_error = bool(isinstance(raw, dict) and raw.get("isError"))
        err = None
    except McpError as e:
        payload = {"ok": False,
                   "error": {"code": "TRANSPORT_ERROR", "message": str(e)}}
        is_error, err = True, str(e)
    dt = time.time() - t0

    rec = {"seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "tool": opts.name, "args": sent,
           "ok": bool(isinstance(payload, dict) and payload.get("ok")),
           "is_error": is_error, "elapsed_ms": round(dt * 1000, 1),
           "result": payload}
    if sent != args:
        rec["args_requested"] = args
        rec["injected"] = note
    if err:
        rec["transport_error"] = err
    _append_trace(trace, rec)

    print("[agent-cli] #%d %s %s %.0f ms  -> %s"
          % (seq, opts.name, "ERR" if is_error else "ok", dt * 1000,
             os.path.relpath(trace)), file=sys.stderr)
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description="Agent Acceptance CLI (MCP only)")
    ap.add_argument("--workdir", default=os.path.join("out", "agent_v08", "default"),
                    help="trace / server.log 放这里（相对仓库根）")
    ap.add_argument("--profile", default=os.environ.get("AGENT_PROFILE"),
                    help="故障注入档位代号（p3a）；也可用环境变量 AGENT_PROFILE 给")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="单次 JSON-RPC 超时（秒），simulate 很慢，默认 600")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools", help="列出所有工具（tools/list）")
    p_schema = sub.add_parser("schema", help="看一个工具的 schema")
    p_schema.add_argument("name", nargs="?")
    p_call = sub.add_parser("call", help="调用一个工具")
    p_call.add_argument("name")
    p_call.add_argument("args_json", help="JSON 对象；@file 或 - 从 stdin 读")

    opts = ap.parse_args(argv)
    workdir = opts.workdir
    if not os.path.isabs(workdir):
        workdir = os.path.join(os.path.dirname(os.path.dirname(HERE)), workdir)
    os.makedirs(workdir, exist_ok=True)
    opts.workdir = workdir

    srv = None
    try:
        srv = McpServer(log_path=os.path.join(workdir, "server.log"),
                        timeout=opts.timeout)
        fn = {"tools": cmd_tools, "schema": cmd_schema, "call": cmd_call}[opts.cmd]
        out = fn(srv, opts)
    except McpError as e:
        out = {"ok": False, "error": {"code": "TRANSPORT_ERROR", "message": str(e)}}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2
    finally:
        if srv is not None:
            srv.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
