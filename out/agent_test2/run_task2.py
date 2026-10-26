# -*- coding: utf-8 -*-
"""Agent Acceptance Test #2 —— 二阶 / 多节点电路。

任务（这次**没有**给任何电路设计思路，只给指标）：

    设计一个 1kHz 正弦输入经过二阶低通滤波器，截止频率约 2kHz，
    要求输出幅值和理论值进行验证。

约束和第一次一样：只用 MCP 的 8 个工具，不 import 项目任何模块、
不调 msbuild、不构造 Circuit IR、不碰 .ms14。

设计决策（Agent 自己做的）：
    二阶 RC 梯形低通，两节相同：R1=R2=R，C1=C2=C
    传函 H(s) = 1 / (1 + 3sRC + (sRC)^2)
    fc = 1 / (2πRC) = 2 kHz  ->  RC = 79.6 us
    取 E12 标准值 R = 10 kΩ、C = 8.2 nF  ->  fc = 1941.0 Hz（-3.0%）
    1 kHz 处理论 |H| = 0.58432、∠H = -64.62°
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mcp_client_min import McpClient   # noqa: E402

TRACE = []
T0 = time.time()


def log(step, tool, args, payload, is_err, dt):
    TRACE.append({"step": step, "tool": tool, "args": args,
                  "ok": not is_err, "ms": round(dt * 1000, 1),
                  "result": payload})
    flag = "ERR " if is_err else "ok  "
    print("%s[%02d] %-14s %6.0f ms" % (flag, step, tool, dt * 1000))


def design():
    R = 10e3
    C = 8.2e-9
    fc = 1.0 / (2 * math.pi * R * C)
    f = 1000.0
    wrc = 2 * math.pi * f * R * C
    # H = 1 / (1 + 3j wRC - (wRC)^2)
    re = 1.0 - wrc ** 2
    im = 3.0 * wrc
    mag = 1.0 / math.hypot(re, im)
    ph = -math.degrees(math.atan2(im, re))
    return {"R": R, "C": C, "fc": fc, "f": f, "gain_theory": mag,
            "phase_theory": ph, "vout_theory": mag * 1.0}


def main():
    d = design()
    print("设计：R=%.0f Ω  C=%.3g F  ->  fc=%.1f Hz" % (d["R"], d["C"], d["fc"]))
    print("理论：1 kHz 处 |H|=%.5f  ∠H=%.2f°  Vout=%.5f V"
          % (d["gain_theory"], d["phase_theory"], d["vout_theory"]))

    cli = McpClient()
    step = 0
    try:
        step += 1
        t = time.time()
        info = cli.request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "agent-2", "version": "1.0"}})
        log(step, "initialize", {}, info.get("serverInfo"), False, time.time() - t)

        step += 1
        t = time.time()
        tools = cli.request("tools/list")
        names = [x["name"] for x in tools["tools"]]
        log(step, "tools/list", {}, names, False, time.time() - t)
        print("    可用工具：%s" % ", ".join(names))

        step += 1
        t = time.time()
        p, e = cli.call("create_circuit", name="agent2_2nd_order_lpf")
        log(step, "create_circuit", {"name": "agent2_2nd_order_lpf"}, p, e,
            time.time() - t)
        cid = p["circuit_id"]

        # ---------- 元件 ----------
        parts = [
            ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1", 1.0, {"frequency": d["f"]}),
            ("RESISTOR", "RESISTOR_VIRTUAL", "R1", d["R"], None),
            ("CAPACITOR", "CAPACITOR_VIRTUAL", "C1", d["C"], None),
            ("RESISTOR", "RESISTOR_VIRTUAL", "R2", d["R"], None),
            ("CAPACITOR", "CAPACITOR_VIRTUAL", "C2", d["C"], None),
            ("POWER_SOURCES", "GROUND", "GND1", None, None),
        ]
        for fam, part, ref, val, extra in parts:
            step += 1
            t = time.time()
            args = {"circuit_id": cid, "family": fam, "part": part,
                    "refdes": ref}
            if val is not None:
                args["value"] = val
            if extra:
                args["parameters"] = extra
            p, e = cli.call("add_component", **args)
            log(step, "add_component", args, p.get("component") if not e else p,
                e, time.time() - t)

        # ---------- 连线 ----------
        nets = [
            [["V1", "+"], ["R1", "1"]],                       # in
            [["R1", "2"], ["C1", "1"], ["R2", "1"]],          # n1
            [["R2", "2"], ["C2", "1"]],                       # n2（输出）
            [["C1", "2"], ["C2", "2"], ["V1", "-"], ["GND1", "1"]],  # 0
        ]
        for pins in nets:
            step += 1
            t = time.time()
            p, e = cli.call("connect", circuit_id=cid, pins=pins)
            log(step, "connect", {"pins": pins},
                p.get("net") if not e else p, e, time.time() - t)

        # ---------- 探针 ----------
        for tgt in ("in", "n2"):
            step += 1
            t = time.time()
            p, e = cli.call("add_probe", circuit_id=cid, target=tgt)
            log(step, "add_probe", {"target": tgt},
                p.get("probe") if not e else p, e, time.time() - t)

        # ---------- 先看一眼电路长什么样 ----------
        step += 1
        t = time.time()
        p, e = cli.call("get_circuit", circuit_id=cid)
        log(step, "get_circuit", {"circuit_id": cid},
            p.get("counts") if not e else p, e, time.time() - t)
        snap = p

        # ---------- 仿真 ----------
        step += 1
        t = time.time()
        p, e = cli.call("simulate", circuit_id=cid, analysis="transient")
        dt = time.time() - t
        log(step, "simulate", {"analysis": "transient"}, p, e, dt)
        sim_err = p if e else None

        result = {"design": d, "circuit_id": cid, "steps": step,
                  "snapshot": snap, "simulate_ok": not e,
                  "simulate_error": sim_err,
                  "sim": p if not e else None}
        if not e:
            sid = p["sim_id"]
            step += 1
            t = time.time()
            m, e2 = cli.call("measure", sim_id=sid)
            log(step, "measure", {"sim_id": sid}, m, e2, time.time() - t)
            result["measure"] = m
            step += 1
            t = time.time()
            w, e3 = cli.call("get_waveform", sim_id=sid, probe_id="P2",
                             max_points=30)
            log(step, "get_waveform", {"sim_id": sid, "probe_id": "P2"},
                w, e3, time.time() - t)
            result["waveform"] = w

    finally:
        cli.close()

    out = os.path.join(HERE, "trace.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("\n" + "=" * 70)
    if result["simulate_ok"]:
        m = result["measure"]
        print("实测增益 %.6f / 相位 %.3f°" % (m["gain"], m["phase_deg"]))
        print("理论增益 %.6f / 相位 %.3f°" % (d["gain_theory"], d["phase_theory"]))
    else:
        print("simulate 失败：")
        print(json.dumps(result["simulate_error"], ensure_ascii=False, indent=2))
    print("=" * 70)
    print("轨迹 -> %s" % out)
    return 0 if result["simulate_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
