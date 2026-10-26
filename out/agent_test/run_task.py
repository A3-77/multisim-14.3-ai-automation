# -*- coding: utf-8 -*-
"""Agent Acceptance Test —— 只用 MCP 的 7 个工具完成一次真实电路设计。

任务（用户原话）：
    创建一个 1V、1kHz 的正弦输入，设计一个截止频率约为 500Hz 的一阶 RC 低通滤波器。
    自行选择电阻和电容值，创建 Multisim 电路，进行瞬态仿真，
    并报告输出端的实际幅值、理论幅值以及误差。

这个脚本扮演"外部 Agent"：除了起 server 子进程和发 JSON-RPC，
不碰本项目任何代码。它不知道 Circuit IR / msbuild / .ms14 长什么样。
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mcp_client_min import McpClient   # 这是我自己写的传输层，不是项目代码

TRACE = []
ERRORS = []


def rec(step, tool, args, payload, is_err, dt=None):
    TRACE.append({"step": step, "tool": tool, "args": args,
                  "ok": not is_err,
                  "error": (payload.get("error") if is_err else None),
                  "ms": round(dt, 2) if dt is not None else None})
    if is_err:
        ERRORS.append({"step": step, "tool": tool, "error": payload.get("error")})


def call(cli, step, tool, **args):
    t0 = time.time()
    payload, is_err = cli.call(tool, **args)
    dt = time.time() - t0
    rec(step, tool, args, payload, is_err, dt)
    tag = "ERR " if is_err else "OK  "
    print("  %s[%02d] %-15s %5.1fs" % (tag, step, tool, dt))
    if is_err:
        e = payload.get("error") or {}
        print("       code   : %s" % e.get("code"))
        print("       message: %s" % e.get("message"))
        if e.get("hint"):
            print("       hint   : %s" % e["hint"])
        if e.get("context"):
            print("       context: %s" % json.dumps(e["context"], ensure_ascii=False))
    return payload, is_err


# ---------------------------------------------------------------------------
# 设计计算（这一步是 Agent 自己的"工程判断"，不经过 MCP）
# ---------------------------------------------------------------------------
def design(fc_target=500.0, f_in=1000.0, v_in=1.0):
    R = 10e3          # E12 标准值
    C = 33e-9         # E12 标准值
    fc = 1.0 / (2 * math.pi * R * C)
    h = 1.0 / math.sqrt(1.0 + (f_in / fc) ** 2)
    ph = -math.degrees(math.atan(f_in / fc))
    return {"R": R, "C": C, "fc": fc, "f_in": f_in, "v_in": v_in,
            "gain_theory": h, "phase_theory": ph,
            "vout_theory": v_in * h, "fc_target": fc_target}


def main():
    print("=" * 78)
    print("AGENT ACCEPTANCE TEST —— 只通过 MCP 的 7 个工具")
    print("=" * 78)

    d = design()
    print("\n[设计] 一阶 RC 低通，目标 fc ≈ 500 Hz，输入 1 V / 1 kHz")
    print("  选 E12 标准值：R = %.0f Ω, C = %.0f nF" % (d["R"], d["C"] * 1e9))
    print("  fc = 1/(2πRC) = %.3f Hz（目标 500 Hz，偏差 %.1f%%）"
          % (d["fc"], (d["fc"] - 500) / 500 * 100))
    print("  理论 |H| = %.6f  ∠H = %.3f°  → Vout = %.6f V"
          % (d["gain_theory"], d["phase_theory"], d["vout_theory"]))

    cli = McpClient()
    try:
        # ---------- 0) 握手 + 读工具清单 ----------
        print("\n[0] 握手 / 读工具清单")
        info = cli.request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "external-agent", "version": "1.0"}})
        cli.notify("notifications/initialized")
        print("  server: %s" % info["serverInfo"])
        tools = cli.request("tools/list")["tools"]
        print("  工具：%s" % ", ".join(t["name"] for t in tools))
        for t in tools:
            req = t["inputSchema"].get("required") or []
            props = list((t["inputSchema"].get("properties") or {}).keys())
            print("    - %-14s 必填=%s  可选=%s"
                  % (t["name"], req, [p for p in props if p not in req]))

        # ---------- 1) 建电路 ----------
        print("\n[1] create_circuit")
        c, err = call(cli, 1, "create_circuit", name="agent_rc_500hz")
        if err:
            return 1
        cid = c["circuit_id"]
        print("       circuit_id = %s" % cid)

        # ---------- 2) 元件 ----------
        print("\n[2] add_component × 4")
        r, err = call(cli, 2, "add_component", circuit_id=cid,
                      family="SIGNAL_VOLTAGE_SOURCES", part="AC_VOLTAGE",
                      refdes="V1", value=d["v_in"], frequency=d["f_in"])
        if not err:
            print("       V1 引脚=%s 别名=%s 参数=%s"
                  % (r["component"]["pins"], r["component"]["aliases"],
                     r["component"].get("parameters")))
        r, err = call(cli, 3, "add_component", circuit_id=cid, family="RESISTOR",
                      part="RESISTOR_VIRTUAL", refdes="R1", value=d["R"])
        r, err = call(cli, 4, "add_component", circuit_id=cid, family="CAPACITOR",
                      part="CAPACITOR_VIRTUAL", refdes="C1", value=d["C"])
        r, err = call(cli, 5, "add_component", circuit_id=cid,
                      family="POWER_SOURCES", part="GROUND", refdes="GND1")
        print("       当前 counts = %s" % (r.get("counts") if not err else "?"))

        # ---------- 3) 连线 ----------
        print("\n[3] connect × 3（不给网络名，看它自己怎么命名）")
        r, err = call(cli, 6, "connect", circuit_id=cid,
                      pins=[["V1", "+"], ["R1", "1"]])
        if not err:
            print("       -> 网络 %r" % r["net"]["name"])
        r, err = call(cli, 7, "connect", circuit_id=cid,
                      pins=[["R1", "2"], ["C1", "1"]])
        if not err:
            mid = r["net"]["name"]
            print("       -> 网络 %r" % mid)
        r, err = call(cli, 8, "connect", circuit_id=cid,
                      pins=[["C1", "2"], ["V1", "-"], ["GND1", "1"]])
        if not err:
            print("       -> 网络 %r" % r["net"]["name"])

        # ---------- 4) 探针 ----------
        print("\n[4] add_probe × 2")
        r, err = call(cli, 9, "add_probe", circuit_id=cid, target="in")
        if not err:
            print("       输入探针 %s @ %s" % (r["probe"]["name"], r["probe"]["net"]))
        r, err = call(cli, 10, "add_probe", circuit_id=cid, target="R1.2")
        if not err:
            print("       输出探针 %s @ %s（用引脚名指定的）"
                  % (r["probe"]["name"], r["probe"]["net"]))

        # ---------- 5) 仿真 ----------
        print("\n[5] simulate（analysis=transient）")
        sim, err = call(cli, 11, "simulate", circuit_id=cid, analysis="transient")
        if err:
            print("\n仿真失败，停止。")
            return 1
        print("       sim_id   = %s" % sim["sim_id"])
        print("       outputs  = %s" % sim["outputs"])
        print("       state    = %s" % sim.get("state"))
        print("       ms14     = %s" % sim.get("ms14"))
        for k, v in sim["summary"].items():
            print("       %-12s n=%d min=%.6f max=%.6f mean=%.6f"
                  % (k, v["n"], v["min"], v["max"], v["mean"]))

        # ---------- 6) 测量 ----------
        print("\n[6] measure(what='all')")
        m, err = call(cli, 12, "measure", sim_id=sim["sim_id"])
        if err:
            return 1
        for name, ch in m["channels"].items():
            print("       %-4s net=%-4s amp=%.6f  phase=%7.3f°  offset=%.6f"
                  % (name, ch["net"], ch.get("amp", float("nan")),
                     ch.get("phase_deg", float("nan")), ch.get("offset", 0.0)))
        print("       mode=%s  gain=%.6f  phase=%.3f°"
              % (m.get("mode"), m.get("gain"), m.get("phase_deg")))
        print("       theory=%s" % json.dumps(m.get("theory"), ensure_ascii=False))

        # ---------- 7) 波形 ----------
        print("\n[7] get_waveform（只取摘要，不拉全量）")
        w, err = call(cli, 13, "get_waveform", sim_id=sim["sim_id"], max_points=20)
        if not err:
            print("       n=%d  t_range=%s  artifact=%s"
                  % (w["n"], w["t_range"], w["artifact"]))
            for nm, ch in w["channels"].items():
                print("       %-12s mean=%.6f min=%.6f max=%.6f preview=%d 点"
                      % (nm, ch["mean"], ch["min"], ch["max"],
                         len(ch["preview"]["t"])))

        # ---------- 8) 额外：错误信息探测（不影响主电路） ----------
        print("\n[8] 额外探测：错误信息够不够 Agent 自纠（明确标注，非任务步骤）")
        p, e1 = call(cli, 14, "add_component", circuit_id=cid, family="INDUCTOR",
                     part="INDUCTOR_VIRTUAL", refdes="L1", value=1e-3)
        p, e2 = call(cli, 15, "simulate", circuit_id=cid, analysis="dc")
        p, e3 = call(cli, 16, "add_probe", circuit_id=cid, target="R1")
        p, e4 = call(cli, 17, "add_component", circuit_id=cid,
                     family="SIGNAL_VOLTAGE_SOURCES", part="AC_VOLTAGE",
                     refdes="V9", value=1.0)

        # ---------- 汇总 ----------
        out = {
            "design": d,
            "circuit_id": cid,
            "sim_id": sim["sim_id"],
            "outputs": sim["outputs"],
            "measure": m,
            "waveform_artifact": w.get("artifact") if not err else None,
            "trace": TRACE,
            "errors": ERRORS,
        }
        with open(os.path.join(HERE, "trace.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")

        # ---------- 判定 ----------
        print("\n" + "=" * 78)
        print("判定（Agent 自己做的，不依赖项目里的判定代码）")
        print("=" * 78)
        p1 = m["channels"].get("P1", {})
        p2 = m["channels"].get("P2", {})
        vout_meas = p2.get("amp")
        vout_th = d["vout_theory"]
        err_pct = (vout_meas - vout_th) / vout_th * 100 if vout_meas else None
        print("  输入实测幅值 : %.6f V（声明 %.1f V）" % (p1.get("amp", 0), d["v_in"]))
        print("  输出实测幅值 : %.6f V" % vout_meas)
        print("  输出理论幅值 : %.6f V" % vout_th)
        print("  误差         : %.3f %%" % err_pct)
        print("  实测增益     : %.6f" % m["gain"])
        print("  理论增益     : %.6f" % d["gain_theory"])
        print("  实测相位     : %.3f°" % m["phase_deg"])
        print("  理论相位     : %.3f°" % d["phase_theory"])
        print("  相位误差     : %.3f°" % (m["phase_deg"] - d["phase_theory"]))
        ok = (abs(err_pct) < 2.0
              and abs(m["phase_deg"] - d["phase_theory"]) < 2.0
              and abs(p1.get("amp", 0) - d["v_in"]) < 0.02 * d["v_in"])
        print("\n  结论：%s" % ("符合一阶 RC 低通理论" if ok else "与理论不符，需要排查"))
        return 0 if ok else 3
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
