# -*- coding: utf-8 -*-
"""MCP 验收客户端（确定性，不接 LLM）。

它做的事和"一个 Agent 会做的事"完全一样：起 server 子进程，走真实 MCP 协议
（JSON-RPC over stdio），用工具把电路建出来、跑完、读数。唯一不同的是这里
把"该建什么电路"写死在代码里，所以结果是可复现的。

两个电路：
    RC 低通   1 V / 1 kHz / 1 kΩ / 159 nF   -> 增益 0.70632，相位 -45.06°
    直流      5 V / 1 kΩ 接地               -> V_R 5 V，R 1000 Ω，I 5 mA

外加四条错误路径，验证错误信息真的能指导 Agent 自纠：
    AC_VOLTAGE + dc          -> ANALYSIS_NOT_SUPPORTED（带 supported 列表）
    并联拓扑                  -> LAYOUT_UNSUPPORTED
    探针目标给元件位号           -> AMBIGUOUS_TARGET
    白名单外元件               -> UNKNOWN_COMPONENT_TYPE

跑法（client 本身不需要 COM，但 server 必须 32 位）：
    python tools/mcp_client.py
    python tools/mcp_client.py --python runtime/py32/python.exe
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(HERE, "mcp_server.py")
OUT_DIR = os.path.join(ROOT, "out", "mcp")

npass = 0
nfail = 0
fails = []


def check(name, cond, detail=""):
    global npass, nfail
    if cond:
        npass += 1
        print("  %-50s OK   %s" % (name, detail))
    else:
        nfail += 1
        fails.append(name)
        print("  %-50s FAIL %s" % (name, detail))


def approx(a, b, tol):
    return a is not None and abs(a - b) <= tol


# ---------------------------------------------------------------------------
class McpClient:
    """最小 MCP 客户端：一次一个请求，按 id 匹配响应。"""

    def __init__(self, python_exe, timeout=300.0):
        self.timeout = timeout
        self.log_path = os.path.join(OUT_DIR, "server.stderr.log")
        os.makedirs(OUT_DIR, exist_ok=True)
        self._log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [python_exe, "-u", SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._log, cwd=ROOT,
            text=True, encoding="utf-8", bufsize=1)
        self._q = queue.Queue()
        self._next_id = 1
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        for line in self.proc.stdout:
            self._q.put(line)

    def _write(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        rid = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

        deadline = time.time() + self.timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise RuntimeError("等 %s 的响应超时（%.0fs）" % (method, self.timeout))
            try:
                line = self._q.get(timeout=min(left, 5.0))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError("server 进程退出了（code=%s），看 %s"
                                       % (self.proc.returncode, self.log_path))
                continue
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except Exception:
                raise RuntimeError("server 输出不是 JSON：%r" % line[:200])
            if resp.get("id") == rid:
                if "error" in resp:
                    raise RuntimeError("JSON-RPC error: %s" % resp["error"])
                return resp.get("result")

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def initialize(self):
        r = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-acceptance-client", "version": "1.0"},
        })
        self.notify("notifications/initialized")
        return r

    def list_tools(self):
        return self.request("tools/list").get("tools") or []

    def call(self, tool, **args):
        """返回 (payload, is_error)。第一个参数故意不叫 name —— 有些工具自己有 name 参数。"""
        res = self.request("tools/call", {"name": tool, "arguments": args})
        is_err = bool(res.get("isError"))
        payload = res.get("structuredContent")
        if payload is None:
            txt = ""
            for c in res.get("content") or []:
                if c.get("type") == "text":
                    txt += c.get("text") or ""
            try:
                payload = json.loads(txt)
            except Exception:
                payload = {"raw": txt}
        return payload, is_err

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        self._log.close()


# ---------------------------------------------------------------------------
def build_rc(cli):
    print("\n[RC 低通] 1 V / 1 kHz / 1 kΩ / 159 nF")
    c = cli.call("create_circuit", name="rc_lowpass_mcp")[0]
    cid = c["circuit_id"]
    check("create_circuit", bool(cid), cid)
    check("初始为空", c["counts"]["components"] == 0, str(c["counts"]))

    r = cli.call("add_component", circuit_id=cid,
                 family="SIGNAL_VOLTAGE_SOURCES", part="AC_VOLTAGE",
                 refdes="V1", value=1.0, frequency=1000.0)[0]
    check("加正弦源（amplitude + frequency 两个语义参数）",
          r["component"]["value"] == 1.0
          and r["component"].get("parameters") == {"frequency": 1000.0},
          str(r["component"].get("parameters")))

    r = cli.call("add_component", circuit_id=cid, family="RESISTOR",
                 part="RESISTOR_VIRTUAL", refdes="R1", value=1000.0)[0]
    check("加 1 kΩ 电阻", r["component"]["value"] == 1000.0)

    r = cli.call("add_component", circuit_id=cid, family="CAPACITOR",
                 part="CAPACITOR_VIRTUAL", refdes="C1", value=159e-9)[0]
    check("加 159 nF 电容", abs(r["component"]["value"] - 159e-9) < 1e-20)

    r = cli.call("add_component", circuit_id=cid, family="POWER_SOURCES",
                 part="GROUND", refdes="GND1")[0]
    check("加地（不需要 value）", r["component"]["value"] is None)

    r = cli.call("connect", circuit_id=cid, pins=[["V1", "+"], ["R1", "1"]])[0]
    check("连 源正极 -> R1.1（自动命名 'in'）", r["net"]["name"] == "in",
          r["net"]["name"])

    r = cli.call("connect", circuit_id=cid, pins=[["R1", "2"], ["C1", "1"]])[0]
    mid = r["net"]["name"]
    check("连 R1.2 -> C1.1（自动命名）", mid in ("n1", "out"), mid)

    r = cli.call("connect", circuit_id=cid,
                 pins=[["C1", "2"], ["V1", "-"], ["GND1", "1"]])[0]
    check("连 回路 -> 地（自动命名 '0'）", r["net"]["name"] == "0",
          r["net"]["name"])

    r = cli.call("add_probe", circuit_id=cid, target="in")[0]
    check("探针 1 放在输入网", r["probe"]["net"] == "in", str(r["probe"]))
    r = cli.call("add_probe", circuit_id=cid, target="R1.2")[0]
    check("探针 2 用引脚名指定（自动解析成网络）", r["probe"]["net"] == mid,
          str(r["probe"]))

    t0 = time.time()
    sim = cli.call("simulate", circuit_id=cid)[0]
    dt = time.time() - t0
    check("simulate 自动选 transient", sim.get("analysis") == "transient",
          "%s，%.1fs" % (sim.get("analysis"), dt))
    check("Multisim 注册了 2 个输出", len(sim.get("outputs") or []) == 2,
          str(sim.get("outputs")))
    check("仿真记录落盘", bool(sim.get("record")), sim.get("record"))

    m = cli.call("measure", sim_id=sim["sim_id"])[0]
    gain = m.get("gain")
    phase = m.get("phase_deg")
    th = m.get("theory") or {}
    print("  实测：增益 %.5f  相位 %.2f°" % (gain, phase))
    print("  理论：|H|=%.5f  ∠H=%.2f°  fc=%.1f Hz"
          % (th.get("gain", float("nan")), th.get("phase_deg", float("nan")),
             th.get("fc", float("nan"))))
    check("增益 ≈ 0.70632", approx(gain, 0.70632, 1e-4), "%.6f" % gain)
    check("相位 ≈ -45.06°", approx(phase, -45.06, 0.05), "%.3f°" % phase)
    check("与理论 |H|=0.70745 差 < 0.002",
          th.get("gain") is not None and abs(gain - th["gain"]) < 0.002,
          "Δ=%.5f" % abs(gain - th["gain"]) if th.get("gain") else "")
    check("与理论 ∠H=-44.97° 差 < 0.2°",
          th.get("phase_deg") is not None
          and abs(phase - th["phase_deg"]) < 0.2,
          "Δ=%.3f°" % abs(phase - th["phase_deg"]) if th.get("phase_deg") else "")

    # what 过滤
    mv = cli.call("measure", sim_id=sim["sim_id"], what="amplitude")[0]
    ch0 = list(mv["channels"].values())[0]
    check("what=amplitude 只返回 amp（不留 mean）",
          "amp" in ch0 and "mean" not in ch0, str(sorted(ch0)))
    check("what 过滤不删身份字段（probe_id 仍在）",
          ch0.get("probe_id") == "P1" and "output" in ch0,
          str({k: ch0.get(k) for k in ("probe_id", "label", "output")}))

    w = cli.call("get_waveform", sim_id=sim["sim_id"], max_points=50)[0]
    check("get_waveform 给摘要而不是整条波形", w["n"] > 1000
          and len(list(w["channels"].values())[0]["preview"]["t"]) <= 60,
          "n=%d preview=%d" % (w["n"],
                               len(list(w["channels"].values())[0]["preview"]["t"])))
    check("get_waveform 给了产物路径", bool(w.get("artifact")), w.get("artifact"))
    check("measure / get_waveform 的 channels 用同一套键",
          set(m["channels"]) == set(w["channels"]) == {"P1", "P2"},
          "%s vs %s" % (sorted(m["channels"]), sorted(w["channels"])))

    w1 = cli.call("get_waveform", sim_id=sim["sim_id"], probe_id="P2")[0]
    check("probe_id 过滤生效", set(w1["channels"]) == {"P2"},
          str(sorted(w1["channels"])))
    check("通道带 Multisim 侧的 label / output 旁证",
          w1["channels"]["P2"].get("label") and w1["channels"]["P2"].get("output"),
          str({k: w1["channels"]["P2"].get(k) for k in ("label", "output")}))

    # get_circuit：只读回读，跨会话核对
    gc = cli.call("get_circuit", circuit_id=cid)[0]
    check("get_circuit 能读回电路", gc["counts"]["components"] == 4,
          str(gc["counts"]))
    check("get_circuit 的 probes 也是 5 字段",
          all(set(x) == {"probe_id", "label", "output", "net", "kind"}
              for x in gc["probes"]), str(gc["probes"]))
    check("仿真过之后 get_circuit 能给出 output 名",
          gc["probes"][0].get("output") == sim["outputs"][0],
          str([x.get("output") for x in gc["probes"]]))

    return cid, sim["sim_id"]


def build_dc(cli):
    print("\n[直流] 5 V / 1 kΩ 接地")
    c = cli.call("create_circuit", name="dc_5v_mcp")[0]
    cid = c["circuit_id"]

    cli.call("add_component", circuit_id=cid, family="POWER_SOURCES",
             part="DC_POWER", refdes="V1", value=5.0)
    cli.call("add_component", circuit_id=cid, family="RESISTOR",
             part="RESISTOR_VIRTUAL", refdes="R1", value=1000.0)
    cli.call("add_component", circuit_id=cid, family="POWER_SOURCES",
             part="GROUND", refdes="GND1")
    cli.call("connect", circuit_id=cid, pins=[["V1", "+"], ["R1", "1"]])
    r = cli.call("connect", circuit_id=cid,
                 pins=[["R1", "2"], ["V1", "-"], ["GND1", "1"]])[0]
    check("直流回路连到地", r["net"]["name"] == "0", r["net"]["name"])
    cli.call("add_probe", circuit_id=cid, target="in")
    cli.call("add_probe", circuit_id=cid, target="0")

    sim = cli.call("simulate", circuit_id=cid)[0]
    check("DC_POWER 默认走 dc", sim.get("analysis") == "dc", sim.get("analysis"))
    check("直流工作点每个探针 1 个点",
          all(v["n"] == 1 for v in sim["summary"].values()),
          str({k: v["n"] for k, v in sim["summary"].items()}))

    m = cli.call("measure", sim_id=sim["sim_id"], what="dc_voltage")[0]
    print("  源网 %.6f V，地网 %.6f V" % (m["v_source_net"], m["v_ground_net"]))
    print("  电阻电压 %.6f V，R=%.4g Ω（%s），I=%.6f A"
          % (m["v_resistor"], m["r"], m["r_source"], m["current"]))
    check("V(source) ≈ 5 V", approx(m["v_source_net"], 5.0, 0.01),
          "%.6f" % m["v_source_net"])
    check("V(ground) ≈ 0 V", approx(m["v_ground_net"], 0.0, 1e-3),
          "%.6f" % m["v_ground_net"])
    check("电阻两端电压 ≈ 5 V", approx(m["v_resistor"], 5.0, 0.01),
          "%.6f" % m["v_resistor"])
    check("R = 1000 Ω（来源 %s）" % m["r_source"], approx(m["r"], 1000.0, 1e-6),
          "%.4f（来源 %s）" % (m["r"], m["r_source"]))
    check("电流 ≈ 5 mA", approx(m["current"], 0.005, 1e-4),
          "%.6f A" % m["current"])
    return cid, sim["sim_id"]


def error_paths(cli, rc_cid):
    print("\n[错误路径] 错误信息必须能指导 Agent 自纠")

    # 1) 源类型与分析类型不匹配
    p, is_err = cli.call("simulate", circuit_id=rc_cid, analysis="dc")
    check("AC_VOLTAGE + dc -> isError", is_err, str(is_err))
    e = p.get("error") or {}
    check("错误码 ANALYSIS_NOT_SUPPORTED", e.get("code") == "ANALYSIS_NOT_SUPPORTED",
          e.get("code"))
    check("错误里说明支持什么", e.get("context", {}).get("supported") == ["transient"],
          str(e.get("context")))
    check("错误里有可执行的 hint",
          bool(e.get("hint")) and "transient" in e["hint"], e.get("hint") or "")

    # 2) 并联拓扑
    c = cli.call("create_circuit", name="parallel_mcp")[0]
    pid = c["circuit_id"]
    cli.call("add_component", circuit_id=pid, family="POWER_SOURCES",
             part="DC_POWER", refdes="V1", value=5.0)
    cli.call("add_component", circuit_id=pid, family="RESISTOR",
             part="RESISTOR_VIRTUAL", refdes="R1", value=1000.0)
    cli.call("add_component", circuit_id=pid, family="RESISTOR",
             part="RESISTOR_VIRTUAL", refdes="R2", value=1000.0)
    cli.call("add_component", circuit_id=pid, family="POWER_SOURCES",
             part="GROUND", refdes="GND1")
    cli.call("connect", circuit_id=pid,
             pins=[["V1", "+"], ["R1", "1"], ["R2", "1"]])
    cli.call("connect", circuit_id=pid,
             pins=[["R1", "2"], ["R2", "2"], ["V1", "-"], ["GND1", "1"]])
    cli.call("add_probe", circuit_id=pid, target="in")
    p, is_err = cli.call("simulate", circuit_id=pid)
    e = p.get("error") or {}
    check("并联 -> LAYOUT_UNSUPPORTED", e.get("code") == "LAYOUT_UNSUPPORTED",
          e.get("code"))
    ctx = e.get("context", {})
    check("错误里标明是哪一类并联（reason=parallel_shunt）",
          ctx.get("reason") == "parallel_shunt", str(ctx.get("reason")))
    check("错误里点名是哪几个元件并联到地",
          ctx.get("shunts") == ["R1", "R2"], str(ctx.get("shunts")))

    # 3) 探针目标给元件位号
    p, is_err = cli.call("add_probe", circuit_id=rc_cid, target="R1")
    e = p.get("error") or {}
    check("target='R1' -> AMBIGUOUS_TARGET", e.get("code") == "AMBIGUOUS_TARGET",
          e.get("code"))
    check("提示里给出正确写法",
          "R1.1" in (e.get("hint") or ""), e.get("hint") or "")

    # 4) 白名单外元件
    p, is_err = cli.call("add_component", circuit_id=rc_cid, family="INDUCTOR",
                         part="INDUCTOR_VIRTUAL", refdes="L1", value=1e-3)
    e = p.get("error") or {}
    check("电感 -> UNKNOWN_COMPONENT_TYPE",
          e.get("code") == "UNKNOWN_COMPONENT_TYPE", e.get("code"))
    check("列出可用元件类型",
          len(e.get("context", {}).get("supported") or []) == 5,
          str(e.get("context", {}).get("supported")))

    # 5) 缺参数
    p, is_err = cli.call("add_component", circuit_id=rc_cid,
                         family="SIGNAL_VOLTAGE_SOURCES", part="AC_VOLTAGE",
                         refdes="V9", value=1.0)
    e = p.get("error") or {}
    check("AC_VOLTAGE 缺 frequency -> MISSING_PARAMETER",
          e.get("code") == "MISSING_PARAMETER", e.get("code"))
    check("错误里点名缺哪个字段",
          e.get("context", {}).get("field") == "frequency", str(e.get("context")))

    # 6) 引脚已属于别的网络
    p, is_err = cli.call("connect", circuit_id=rc_cid,
                         pins=[["R1", "2"], ["V1", "+"]])
    e = p.get("error") or {}
    check("跨网络硬连 -> PIN_ALREADY_CONNECTED",
          e.get("code") == "PIN_ALREADY_CONNECTED", e.get("code"))


def main():
    ap = argparse.ArgumentParser(description="MCP 电路执行器验收")
    ap.add_argument("--python", default=os.path.join(ROOT, "runtime", "py32",
                                                     "python.exe"),
                    help="跑 server 的解释器（必须 32 位）")
    args = ap.parse_args()

    if not os.path.isfile(args.python):
        print("找不到 32 位 Python：%s" % args.python, file=sys.stderr)
        return 4

    print("=" * 78)
    print("MCP 电路执行器 —— 确定性验收（走真实 MCP 协议）")
    print("=" * 78)
    print("server: %s" % SERVER)
    print("python: %s" % args.python)

    cli = McpClient(args.python)
    try:
        print("\n[0] 握手")
        info = cli.initialize()
        check("initialize 返回 serverInfo",
              info.get("serverInfo", {}).get("name") == "multisim-circuit",
              str(info.get("serverInfo")))
        tools = cli.list_tools()
        names = [t["name"] for t in tools]
        want = ["create_circuit", "add_component", "connect", "add_probe",
                "get_circuit", "simulate", "measure", "get_waveform"]
        check("tools/list 正好 8 个工具", names == want, str(names))
        check("每个工具都有 inputSchema",
              all("inputSchema" in t for t in tools))
        check("schema 里不出现 Multisim 内部概念",
              not any(k in json.dumps(tools, ensure_ascii=False)
                      for k in ("CiID", "CiPort", "CIITSymbolComp", "SimState")),
              "已检查 CiID/CiPort/CIITSymbolComp/SimState")

        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "tools_schema.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"tools": tools}, f, ensure_ascii=False, indent=2)
            f.write("\n")

        rc_cid, rc_sid = build_rc(cli)
        dc_cid, dc_sid = build_dc(cli)
        error_paths(cli, rc_cid)

        # 会话目录里确实有产物
        sess = os.path.join(ROOT, "out", "mcp", "sessions")
        for cid in (rc_cid, dc_cid):
            d = os.path.join(sess, cid)
            check("会话 %s 落盘完整" % cid[:8],
                  os.path.isfile(os.path.join(d, "circuit.ir.json"))
                  and os.path.isfile(os.path.join(d, "session.json")),
                  d)

        summary = {
            "rc": {"circuit_id": rc_cid, "sim_id": rc_sid},
            "dc": {"circuit_id": dc_cid, "sim_id": dc_sid},
            "pass": nfail == 0, "fails": list(fails),
            "tools": names,
        }
        with open(os.path.join(OUT_DIR, "acceptance.json"), "w",
                  encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            f.write("\n")
    finally:
        cli.close()

    print()
    print("=" * 78)
    print("总计 %d 项通过，%d 项失败 => %s"
          % (npass, nfail, "全部通过" if nfail == 0 else "失败项 %s" % fails))
    print("=" * 78)
    return 0 if nfail == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
