# -*- coding: utf-8 -*-
"""最小 MCP stdio 客户端 —— 纯标准库，**不 import 本项目任何模块**。

为什么这个文件必须"什么都不懂"
------------------------------
v0.8.0 要回答的问题是：

    一个只见过 MCP `tools/list` 的 LLM Agent，
    能不能自己把电路设计 → 建模 → 仿真 → 验算走完？

所以被测对象（MCP server）和测试者之间只能有 JSON-RPC。这个客户端就是那条
边界：它知道怎么起子进程、怎么发一行 JSON、怎么读一行 JSON，除此之外
不知道 Multisim、不知道 Circuit IR、不知道 msbuild，也不 import 它们。

一个刻意的设计：**每次调用起一个新的 server 进程**
--------------------------------------------------
server 是无状态的（状态在 `out/mcp/sessions/<circuit_id>/` 的磁盘上），
所以"一个 CLI 进程 = 一次工具调用"完全成立。好处是 Agent 的每次调用都
不能依赖进程内隐藏状态 —— 它必须真的用 `circuit_id` / `sim_id` 把上下文
带过去。这正是我们要验的东西之一。

用法
----
    from mcp_stdio import McpServer
    s = McpServer(log_path="server.log")
    print(s.request("tools/list"))
    print(s.request("tools/call", {"name": "create_circuit", "arguments": {}}))
    s.close()
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERVER = os.path.join(ROOT, "tools", "mcp_server.py")
PY32 = os.path.join(ROOT, "runtime", "py32", "python.exe")
PROTOCOL_VERSION = "2024-11-05"


class McpError(RuntimeError):
    pass


class McpServer(object):
    """一个 server 子进程 + 一条 JSON-RPC 连接。"""

    def __init__(self, log_path=None, timeout=600.0):
        self.timeout = float(timeout)
        self._id = 0
        self._q = queue.Queue()
        self._closed = False
        python = PY32 if os.path.isfile(PY32) else sys.executable
        if not os.path.isfile(SERVER):
            raise McpError("找不到 MCP server：%s" % SERVER)

        if log_path:
            os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
            self._log = open(log_path, "a", encoding="utf-8")
        else:
            self._log = subprocess.DEVNULL

        self.proc = subprocess.Popen(
            [python, "-u", SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
            cwd=ROOT, text=True, encoding="utf-8", bufsize=1)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self.server_info = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agent-acceptance-cli", "version": "0.8.0"},
        })
        # MCP 规定 initialize 之后要发一条 initialized 通知
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # ---------------------------------------------------------------- 传输
    def _read_loop(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            self._q.put(line)

    def _write(self, obj):
        if self._closed:
            raise McpError("连接已关闭")
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self._id += 1
        rid = self._id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

        deadline = time.time() + self.timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise McpError("等 %s 的响应超时（%.0f s）" % (method, self.timeout))
            try:
                line = self._q.get(timeout=min(left, 5.0))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise McpError("server 进程已退出（returncode=%s）"
                                   % self.proc.returncode)
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                # stdout 上出现非 JSON —— 按 MCP 规定这是协议违规，直接报
                raise McpError("server 往 stdout 写了非 JSON：%r" % line[:200])
            if obj.get("id") != rid:
                continue                      # 不是这次的响应（通知/乱序）
            if "error" in obj:
                raise McpError("JSON-RPC error: %s" % json.dumps(
                    obj["error"], ensure_ascii=False))
            return obj.get("result")

    # ---------------------------------------------------------------- 高层
    def list_tools(self):
        return (self.request("tools/list") or {}).get("tools") or []

    def call_tool(self, name, arguments=None):
        return self.request("tools/call",
                            {"name": name, "arguments": arguments or {}})

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        if self._log is not subprocess.DEVNULL:
            try:
                self._log.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
