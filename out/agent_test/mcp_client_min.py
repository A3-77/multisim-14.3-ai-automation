# -*- coding: utf-8 -*-
"""外部 Agent 的 MCP 客户端 —— 只依赖标准库，不 import 本项目任何模块。

这是一个"使用者 Agent"视角的最小实现：它只会做三件事
    1. 起 MCP server 子进程
    2. 发 JSON-RPC（initialize / tools/list / tools/call）
    3. 打印返回值

它不知道 Multisim、不知道 Circuit IR、不知道 msbuild ——
这正是这次验收要验证的前提。
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER = os.path.join(ROOT, "tools", "mcp_server.py")
PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")


class McpClient:
    def __init__(self, timeout=420.0):
        self.timeout = timeout
        self._log = open(LOG, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [PY, "-u", SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
            cwd=ROOT, text=True, encoding="utf-8", bufsize=1)
        self._q = queue.Queue()
        self._id = 1
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.proc.stdout:
            self._q.put(line)

    def _write(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        rid = self._id
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        deadline = time.time() + self.timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise RuntimeError("等 %s 超时" % method)
            try:
                line = self._q.get(timeout=min(left, 5.0))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError("server 退出了 code=%s" % self.proc.returncode)
                continue
            line = line.strip()
            if not line:
                continue
            resp = json.loads(line)
            if resp.get("id") == rid:
                if "error" in resp:
                    raise RuntimeError("JSON-RPC error: %s" % resp["error"])
                return resp.get("result")

    def notify(self, method, params=None):
        m = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            m["params"] = params
        self._write(m)

    def call(self, tool, **args):
        """返回 (payload, is_error)。"""
        res = self.request("tools/call", {"name": tool, "arguments": args})
        payload = res.get("structuredContent")
        if payload is None:
            txt = "".join(c.get("text") or "" for c in res.get("content") or [])
            try:
                payload = json.loads(txt)
            except Exception:
                payload = {"raw": txt}
        return payload, bool(res.get("isError"))

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
