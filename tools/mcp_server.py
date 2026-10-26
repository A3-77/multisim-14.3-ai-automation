# -*- coding: utf-8 -*-
"""Multisim 电路执行器 —— MCP Server（stdio 传输，纯标准库）。

为什么不用第三方 MCP SDK
------------------------
这个仓库的硬约束是"零第三方依赖 + 必须 32 位 Python"（COM 限制）。
MCP 的 stdio 传输就是「一行一个 JSON-RPC 2.0 消息」，实现一个够用的子集
比引入依赖并让它兼容 32 位环境更省事。这里只实现 Agent 真正会用到的三条：
    initialize / tools/list / tools/call

七个工具（都在 circuit_session 里实现，这里只做协议适配）
--------------------------------------------------------
    create_circuit    建会话，拿 circuit_id
    add_component     加元件（语义参数：amplitude / frequency / resistance）
    connect           连网络（自动命名、自动判重）
    add_probe         加探针（按网络名或引脚，自动唯一命名）
    simulate          transient / dc，自动布局 + 编译 + 跑 Multisim
    measure           增益 / 相位 / 幅值 / 直流电压
    get_waveform      波形摘要 + 预览 + 产物路径

stdout 只走协议
---------------
启动时把 sys.stdout 换到 stderr，所有 print（包括 ir_sim 里的）都不会污染
JSON-RPC 流。真正的协议输出走保存下来的 `_PROTO_OUT`。这一条是硬的：
任何一行非 JSON 写到 stdout，客户端立刻解析失败。

跑法（必须 32 位 Python，COM 限制）
-----------------------------------
    runtime\\py32\\python.exe -u tools\\mcp_server.py
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------- stdout 保护
_PROTO_OUT = sys.stdout
try:
    _PROTO_OUT.reconfigure(encoding="utf-8", newline="\n")
except Exception:
    pass
sys.stdout = sys.stderr          # 任何 print 都去 stderr
try:
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

import circuit_session as S     # noqa: E402

SERVER_NAME = "multisim-circuit"
SERVER_VERSION = "0.6.0"
PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# 工具 schema
#
# description 是写给 Agent 看的：说清楚"什么时候用"和"什么时候不该用"，
# 比列参数更重要。错误提示里也会引用这些约束。
# ---------------------------------------------------------------------------
_CID = {"type": "string",
        "description": "create_circuit 返回的 circuit_id，形如 c-1a2b3c4d5e"}

TOOLS = [
    {
        "name": "create_circuit",
        "description": (
            "创建一个新的空电路会话，返回 circuit_id。之后所有 add_component / "
            "connect / add_probe 都要带上这个 id。不会立刻生成 .ms14 —— "
            "编译发生在 simulate 时。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "给电路起个名字（可读，会用于产物文件名）"},
            },
        },
    },
    {
        "name": "add_component",
        "description": (
            "往电路里加一个元件。只接受已验证过真机仿真的五种：\n"
            "  SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE（正弦源，需要 amplitude + frequency）\n"
            "  POWER_SOURCES/DC_POWER（直流源，需要 voltage）\n"
            "  RESISTOR/RESISTOR_VIRTUAL（需要 resistance，单位 Ω）\n"
            "  CAPACITOR/CAPACITOR_VIRTUAL（需要 capacitance，单位 F）\n"
            "  POWER_SOURCES/GROUND（接地，不需要 value）\n"
            "不要传坐标 —— 布局由 simulate 自动算。refdes 不传就自动编号。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "family": {"type": "string",
                           "description": "元件家族，如 RESISTOR / POWER_SOURCES"},
                "part": {"type": "string",
                         "description": "具体型号，如 RESISTOR_VIRTUAL / DC_POWER"},
                "refdes": {"type": "string",
                           "description": "位号（V1 / R1 / C1 / GND1）。不传则自动编号"},
                "value": {"type": "number",
                          "description": "元件值：幅值 V / 电压 V / 阻值 Ω / 容值 F"},
                "frequency": {"type": "number",
                              "description": "仅 AC_VOLTAGE 需要，单位 Hz"},
                "params": {"type": "object",
                           "description": "高级用法：直接给底层参数序号。一般不要用"},
            },
            "required": ["circuit_id", "family", "part"],
        },
    },
    {
        "name": "connect",
        "description": (
            "把若干引脚连到同一条网络上。引脚写法：[\"V1\",\"+\"] 或 \"V1.+\"。\n"
            "网络名可以不给：含地的网络会自动叫 '0'，含电源正极的自动叫 'in'，"
            "其余 n1/n2。也可以给一个名字把引脚追加到已有网络。\n"
            "同一个引脚不能属于两条网络。不要传坐标。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "pins": {"type": "array",
                         "description": "引脚数组，如 [[\"V1\",\"+\"],[\"R1\",\"1\"]]",
                         "items": {}},
                "net": {"type": "string",
                        "description": "网络名。不传则自动命名"},
            },
            "required": ["circuit_id", "pins"],
        },
    },
    {
        "name": "add_probe",
        "description": (
            "在某个网络上放一个电压探针。target 可以是网络名（'out'）、"
            "引脚（'R1.2'，自动解析成它所在的网络）。\n"
            "不要传元件位号（'R1'）—— 两端元件有两个引脚，会报 AMBIGUOUS_TARGET。\n"
            "最多 9 个探针（LocalName 序号超过一位数字的命名规则还没验证）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "target": {"type": "string",
                           "description": "网络名（'in'）或引脚（'R1.2'）"},
                "name": {"type": "string",
                         "description": "探针名。不传则自动编号 P1/P2/..."},
            },
            "required": ["circuit_id", "target"],
        },
    },
    {
        "name": "simulate",
        "description": (
            "编译并真跑 Multisim，返回仿真句柄 sim_id。\n"
            "analysis 可选 transient（时域）或 dc（直流工作点，单点）。\n"
            "源类型与分析的匹配是强制的：AC_VOLTAGE 只能 transient，"
            "DC_POWER 默认 dc（也允许 transient）。不匹配会返回 "
            "ANALYSIS_NOT_SUPPORTED 并告诉你该改成什么。\n"
            "transient 不传 stop / sample_rate 时按信号频率自动推算（6 个周期、"
            "每周期 200 点）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "circuit_id": _CID,
                "analysis": {"type": "string", "enum": ["transient", "dc"],
                             "description": "分析类型。不传则按源类型自动选"},
                "start": {"type": "number", "description": "起始时间 s（仅 transient）"},
                "stop": {"type": "number", "description": "结束时间 s（仅 transient）"},
                "sample_rate": {"type": "number",
                                "description": "采样率 Hz（仅 transient）"},
            },
            "required": ["circuit_id"],
        },
    },
    {
        "name": "measure",
        "description": (
            "从一次仿真里取测量值。what 决定返回哪些字段：\n"
            "  all（默认）      全部：均值 / RMS / 幅值 / 相位 / 增益\n"
            "  voltage          每通道的 mean / rms / min / max\n"
            "  amplitude        每通道的正弦拟合幅值（仅 transient）\n"
            "  phase            每通道相位（仅 transient）\n"
            "  dc_voltage       每通道直流电压（仅 dc）\n"
            "transient 会额外给 gain / phase_deg / theory；dc 会给 "
            "v_resistor / current（I = V_R / R，R 来自 Multisim RLCValue）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sim_id": {"type": "string", "description": "simulate 返回的 sim_id"},
                "what": {"type": "string",
                         "enum": ["all", "voltage", "amplitude", "phase",
                                  "dc_voltage"]},
                "probe": {"type": "string",
                          "description": "只看某一个探针（探针名，如 P1）"},
            },
            "required": ["sim_id"],
        },
    },
    {
        "name": "get_waveform",
        "description": (
            "取波形数据。不会把整条波形塞进返回值：默认只给摘要（n / min / max / "
            "mean / 时间范围）+ 最多 max_points 个采样点的预览，完整数据在 "
            "artifact 指向的 CSV 里。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sim_id": {"type": "string", "description": "simulate 返回的 sim_id"},
                "probe": {"type": "string", "description": "只看某个通道的输出名"},
                "max_points": {"type": "integer",
                               "description": "预览采样点上限，默认 200，最大 5000"},
            },
            "required": ["sim_id"],
        },
    },
]

_DISPATCH = {
    "create_circuit": S.create_circuit,
    "add_component": S.add_component,
    "connect": S.connect,
    "add_probe": S.add_probe,
    "simulate": S.simulate,
    "measure": S.measure,
    "get_waveform": S.get_waveform,
}


# ---------------------------------------------------------------------------
# JSON-RPC
# ---------------------------------------------------------------------------
def _send(obj):
    line = json.dumps(obj, ensure_ascii=False)
    _PROTO_OUT.write(line + "\n")
    _PROTO_OUT.flush()


def _ok(rid, result):
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _fail(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _send({"jsonrpc": "2.0", "id": rid, "error": err})


def _text_result(payload, is_error=False):
    """MCP tools/call 的返回：content 文本 + structuredContent 两份都给。

    文本那份是给只看 content 的客户端；structuredContent 给能解析结构的客户端。
    两份内容一致，避免 Agent 在不同客户端上看到不同的东西。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    out = {"content": [{"type": "text", "text": text}]}
    if isinstance(payload, dict):
        out["structuredContent"] = payload
    if is_error:
        out["isError"] = True
    return out


def _call_tool(name, args):
    fn = _DISPATCH.get(name)
    if fn is None:
        return _text_result({"ok": False,
                             "error": {"code": "UNKNOWN_TOOL",
                                       "message": "没有这个工具：%r" % name,
                                       "hint": "可用：%s" % ", ".join(_DISPATCH)}},
                            is_error=True)
    try:
        payload = fn(**args)
        if isinstance(payload, dict):
            payload.setdefault("ok", True)
        return _text_result(payload)
    except S.SessionError as e:
        return _text_result({"ok": False, "error": e.to_dict()}, is_error=True)
    except TypeError as e:
        return _text_result(
            {"ok": False,
             "error": {"code": "BAD_ARGUMENT",
                       "message": "参数不对：%s" % e,
                       "hint": "对照 tools/list 里这个工具的 inputSchema。"}},
            is_error=True)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return _text_result(
            {"ok": False,
             "error": {"code": "INTERNAL", "message": "%s: %s"
                        % (type(e).__name__, e),
                        "hint": "这是内部错误，不是你的参数问题；"
                                "看 server 的 stderr。"}},
            is_error=True)


def handle(msg):
    if not isinstance(msg, dict):
        return
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}

    # 通知（没有 id）不需要响应
    is_notification = "id" not in msg

    if method == "initialize":
        _ok(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "这是 Multisim 电路执行器。典型流程："
                "create_circuit -> add_component × N -> connect -> add_probe -> "
                "simulate -> measure / get_waveform。"
                "不要传坐标，布局由 simulate 自动算。"
                "只支持单电源串联链到地的拓扑（并联会报 LAYOUT_UNSUPPORTED）。"
            ),
        })
        return

    if is_notification:
        return

    if method == "ping":
        _ok(rid, {})
        return

    if method == "tools/list":
        _ok(rid, {"tools": TOOLS})
        return

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            _fail(rid, -32602, "arguments 必须是对象")
            return
        _ok(rid, _call_tool(name, args))
        return

    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        _ok(rid, {key: []})
        return

    _fail(rid, -32601, "Method not found: %r" % method)


def main():
    print("[mcp] %s v%s 就绪（python %s, %d 位）"
          % (SERVER_NAME, SERVER_VERSION, sys.version.split()[0],
             64 if sys.maxsize > 2 ** 32 else 32), file=sys.stderr)
    print("[mcp] 会话目录 %s" % S.SESS_ROOT, file=sys.stderr)
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            _fail(None, -32700, "JSON 解析失败：%s" % e)
            continue
        if isinstance(msg, list):
            for m in msg:
                handle(m)
        else:
            handle(msg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
