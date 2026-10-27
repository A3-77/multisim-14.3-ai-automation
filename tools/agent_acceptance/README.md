# Agent Acceptance 测试台（v0.8.0）

> 这个目录回答一个问题：
>
> **一个只见过 MCP `tools/list` 的 LLM Agent，能不能自己完成
> "读需求 → 选拓扑 → 定 R/C → 建电路 → 仿真 → 测量 → 验算"？**
>
> 报告：[`docs/agent-acceptance-v0.8.md`](../../docs/agent-acceptance-v0.8.md)

这里没有"跑一遍脚本"的快捷方式。三个文件各管一件事：

| 文件 | 作用 | 会不会 import 项目代码 |
| --- | --- | --- |
| `mcp_stdio.py` | 最小 MCP stdio 客户端（起 server 子进程、发一行 JSON、读一行 JSON） | **不会**，只用标准库 |
| `agent_cli.py` | Agent 唯一入口：`tools` / `schema` / `call`，每次调用写一条 trace | 只 import `mcp_stdio` |
| `verify_sim.py` | 不信 `measure`：从原始 CSV 独立重算 amp / phase 并对账 | **不会**，拟合是自己写的 |
| `summarize.py` | trace.jsonl → 调用序列表格 + 统计（错误数 / 重复调用 / 耗时） | 不会 |

## 为什么每次调用都新起一个 server 进程

server 是无状态的（电路存在 `out/mcp/sessions/<circuit_id>/`），所以
"一个 CLI 进程 = 一次工具调用"成立。这样 Agent **没法依赖进程内的隐藏状态**：
它必须真的把 `circuit_id` / `sim_id` 带过去。这正是要验的能力之一。

## 跑法

```bash
# 看工具（这就是 Agent 能看到的全部 API 文档）
runtime/py32/python.exe tools/agent_acceptance/agent_cli.py \
    --workdir out/agent_v08/p1 tools

# 调一个工具
runtime/py32/python.exe tools/agent_acceptance/agent_cli.py \
    --workdir out/agent_v08/p1 call create_circuit '{"name":"rc_1st"}'

# 参数太长就写文件
runtime/py32/python.exe tools/agent_acceptance/agent_cli.py \
    --workdir out/agent_v08/p1 call add_component @args.json
```

stdout 永远是一个 JSON 对象（工具返回的 payload），过程信息走 stderr。
`--workdir` 下会产生：

```
trace.jsonl    每次 tools/call 的完整 args + result（报告的唯一数据源）
server.log     server 的 stderr（启动日志、traceback）
```

## 故障注入

```bash
--profile case1-missing-frequency
```

第一次 `add_component` 一个 `AC_VOLTAGE` 时，把 `frequency` / `parameters`
摘掉，让 server 真的返回 `MISSING_PARAMETER`。**只注入一次**，并且会在
trace 里写 `"injected": "..."` —— 这样"Agent 缺参数恢复"是被测出来的，
不是被提示出来的。

## 验收后核对

```bash
# 调用序列 + 统计
runtime/py32/python.exe tools/agent_acceptance/summarize.py \
    out/agent_v08/p1/trace.jsonl --md out/agent_v08/p1/calls.md

# 独立复算（防"measure 是编的"）
runtime/py32/python.exe tools/agent_acceptance/verify_sim.py \
    --trace out/agent_v08/p1/trace.jsonl --sim s-xxxxxxxxxx
```

`verify_sim.py` 的 `checks.recompute.consistent=true` 意味着
**从 CSV 复算的 amp / phase 与 `measure` 返回的完全一致**（差值 0），
同时它会打印 `.ms14` 的字节数、CSV 行数、仿真 state 和 timing。
