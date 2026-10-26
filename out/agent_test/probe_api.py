# -*- coding: utf-8 -*-
"""API 边界探测 —— 只调用 MCP 工具，不改任何代码。

目的：为 Agent Acceptance Report 的第 10/11 项提供证据。
探测的都是"一个不了解实现的 Agent 会自然犯的错"。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mcp_client_min import McpClient

CID = "c-eccf480d70"
SID = "s-042f992be7"

results = []


def probe(cli, label, tool, **args):
    payload, is_err = cli.call(tool, **args)
    e = payload.get("error") or {}
    print("\n--- %s" % label)
    print("    %s(%s)" % (tool, json.dumps(args, ensure_ascii=False)))
    if is_err:
        print("    -> ERR %s" % e.get("code"))
        print("       %s" % e.get("message"))
        if e.get("hint"):
            print("       hint: %s" % e["hint"])
        if e.get("context"):
            print("       ctx : %s" % json.dumps(e["context"], ensure_ascii=False)[:160])
    else:
        print("    -> OK  %s" % json.dumps(
            {k: v for k, v in payload.items() if k in
             ("analysis", "n", "artifact", "channels", "gain", "mode")},
            ensure_ascii=False)[:200])
    results.append({"label": label, "tool": tool, "args": args,
                    "ok": not is_err, "error": e or None})
    return payload, is_err


def main():
    cli = McpClient()
    try:
        cli.request("initialize", {"protocolVersion": "2024-11-05",
                                   "capabilities": {},
                                   "clientInfo": {"name": "probe", "version": "1"}})
        cli.notify("notifications/initialized")

        print("=" * 78)
        print("API 边界探测（全部通过 MCP，不改代码）")
        print("=" * 78)

        # 1) schema 说 probe 是"输出名"，实现按探针名 —— 哪个对？
        probe(cli, "get_waveform 的 probe 传 COM 输出名（schema 字面意思）",
              "get_waveform", sim_id=SID, probe="V(探针1)")
        probe(cli, "get_waveform 的 probe 传探针名", "get_waveform",
              sim_id=SID, probe="P1")
        probe(cli, "measure 的 probe 传 COM 输出名", "measure",
              sim_id=SID, probe="V(探针1)")
        probe(cli, "measure 的 probe 传探针名", "measure", sim_id=SID, probe="P1")

        # 2) 新建一个"忘了接地"的电路，看错误够不够指导
        c = cli.call("create_circuit", name="forgot_ground")[0]
        nid = c["circuit_id"]
        cli.call("add_component", circuit_id=nid, family="POWER_SOURCES",
                 part="DC_POWER", refdes="V1", value=5.0)
        cli.call("add_component", circuit_id=nid, family="RESISTOR",
                 part="RESISTOR_VIRTUAL", refdes="R1", value=1000.0)
        cli.call("connect", circuit_id=nid, pins=[["V1", "+"], ["R1", "1"]])
        cli.call("connect", circuit_id=nid, pins=[["V1", "-"], ["R1", "2"]])
        cli.call("add_probe", circuit_id=nid, target="in")
        probe(cli, "忘了接地就 simulate", "simulate", circuit_id=nid)

        # 3) 引脚名写错
        probe(cli, "引脚名写错（V1.3）", "connect", circuit_id=CID,
              pins=[["V1", "3"], ["R1", "1"]])

        # 4) 不存在的 circuit_id（Agent 记错了）
        probe(cli, "circuit_id 记错", "simulate", circuit_id="c-0000000000")

        # 5) 不存在的 sim_id
        probe(cli, "sim_id 记错", "measure", sim_id="s-0000000000")

        # 6) 跨会话恢复：有没有工具能查已有电路？
        probe(cli, "想知道已建电路当前长什么样（没有 get_circuit）",
              "get_circuit", circuit_id=CID)

        # 7) 串联链超过 2 个无源元件
        c2 = cli.call("create_circuit", name="three_passives")[0]
        tid = c2["circuit_id"]
        cli.call("add_component", circuit_id=tid, family="POWER_SOURCES",
                 part="DC_POWER", refdes="V1", value=5.0)
        for i in (1, 2, 3):
            cli.call("add_component", circuit_id=tid, family="RESISTOR",
                     part="RESISTOR_VIRTUAL", refdes="R%d" % i, value=1000.0)
        cli.call("add_component", circuit_id=tid, family="POWER_SOURCES",
                 part="GROUND", refdes="GND1")
        cli.call("connect", circuit_id=tid, pins=[["V1", "+"], ["R1", "1"]])
        cli.call("connect", circuit_id=tid, pins=[["R1", "2"], ["R2", "1"]])
        cli.call("connect", circuit_id=tid, pins=[["R2", "2"], ["R3", "1"]])
        cli.call("connect", circuit_id=tid,
                 pins=[["R3", "2"], ["V1", "-"], ["GND1", "1"]])
        cli.call("add_probe", circuit_id=tid, target="in")
        probe(cli, "串联链 3 个无源元件", "simulate", circuit_id=tid)

        with open(os.path.join(HERE, "api_probe.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("\n结果 -> out/agent_test/api_probe.json")
    finally:
        cli.close()


if __name__ == "__main__":
    main()
