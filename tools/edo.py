# -*- coding: utf-8 -*-
"""向提权助手发指令并等结果。"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")
CMD = os.path.join(OUT, "ecmd.json")
RES = os.path.join(OUT, "eres.json")
HB = os.path.join(OUT, "ehb.txt")


def send(cmd, timeout=120):
    if not os.path.exists(HB):
        return {"ok": False, "err": "提权助手没在运行"}
    if os.path.exists(RES):
        os.remove(RES)
    json.dump(cmd, open(CMD, "w", encoding="utf-8"), ensure_ascii=False)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(RES):
            time.sleep(0.1)
            return json.load(open(RES, encoding="utf-8"))
        time.sleep(0.2)
    return {"ok": False, "err": "超时"}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0].startswith("{"):
        cmd = json.loads(args[0])
    elif args and args[0] == "open":
        cmd = {"op": "open", "path": os.path.abspath(args[1])}
    elif args and args[0] == "shot":
        cmd = {"op": "shot", "name": args[1]}
    else:
        cmd = {"op": args[0] if args else "wins"}
    print(json.dumps(send(cmd), ensure_ascii=False, indent=2)[:3000])
