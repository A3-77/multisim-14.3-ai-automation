# -*- coding: utf-8 -*-
"""向常驻驱动发一条指令并等待结果。用法：
  python tools/do.py '{"op":"shot","name":"x"}'
  python tools/do.py key ctrl o
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")
CMD = os.path.join(OUT, "cmd.json")
RES = os.path.join(OUT, "res.json")


def send(cmd, timeout=40):
    if os.path.exists(RES):
        os.remove(RES)
    with open(CMD, "w", encoding="utf-8") as f:
        json.dump(cmd, f, ensure_ascii=False)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(RES):
            time.sleep(0.1)
            with open(RES, encoding="utf-8") as f:
                return json.load(f)
        time.sleep(0.15)
    return {"ok": False, "err": "超时（驱动没响应）"}


def main():
    args = sys.argv[1:]
    if not args:
        print("需要指令")
        return
    if args[0].startswith("{"):
        cmd = json.loads(args[0])
    elif args[0] == "key":
        cmd = {"op": "key", "keys": args[1:]}
    elif args[0] == "shot":
        cmd = {"op": "shot", "name": args[1]}
    elif args[0] == "type":
        cmd = {"op": "type", "text": " ".join(args[1:])}
    else:
        cmd = {"op": args[0]}
    print(json.dumps(send(cmd), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
