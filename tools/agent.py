# -*- coding: utf-8 -*-
"""给常驻提权代理发指令的客户端。

用法（作为库）：
    import agent
    print(agent.call({"op": "ping"}))
    print(agent.verify("out/acceptance.ms14", shot="out/shots/acc.png"))
"""
import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
Q = os.path.join(ROOT, "out", "q")
CMD = os.path.join(Q, "cmd")
RES = os.path.join(Q, "res")
HB = os.path.join(Q, "hb.txt")


def alive(max_age=6.0):
    if not os.path.exists(HB):
        return False
    try:
        return (time.time() - os.path.getmtime(HB)) < max_age
    except OSError:
        return False


def call(req, timeout=180):
    os.makedirs(CMD, exist_ok=True)
    os.makedirs(RES, exist_ok=True)
    name = "%s_%s.json" % (time.strftime("%H%M%S"), uuid.uuid4().hex[:6])
    tmp = os.path.join(CMD, name + ".tmp")
    json.dump(req, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, os.path.join(CMD, name))
    out = os.path.join(RES, name)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(out):
            try:
                res = json.load(open(out, encoding="utf-8"))
            except Exception:
                time.sleep(0.2)
                continue
            os.remove(out)
            return res
        time.sleep(0.4)
    raise TimeoutError("代理 %ds 内没回结果（它活着吗？）" % timeout)


def verify(path, shot=None, keep=False, timeout=180):
    req = {"op": "verify", "file": path, "keep": keep}
    if shot:
        req["shot"] = shot
    return call(req, timeout=timeout)


if __name__ == "__main__":
    if not alive():
        print("代理未运行，请先执行 tools/agent_launch.py")
        sys.exit(1)
    print(call({"op": "ping"}))
