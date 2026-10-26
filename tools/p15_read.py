# -*- coding: utf-8 -*-
"""P15 通用读数：开一个 .ms14，跑瞬态，打印探针波形统计。一文件一进程。

用法：
  runtime\\py32\\python.exe tools\\p15_read.py out/p15_div.ms14 [--json out/x.json]

输出（stdout 一行一项，便于人读）：
  元件 / 输出名 / RLC 读数 / V 统计 / state_seq / 错误原文
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SEC = 0.001
NSAMP = 2000
RATE = NSAMP / SEC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--json", default=None)
    ap.add_argument("--sec", type=float, default=SEC)
    a = ap.parse_args()

    src = a.file if os.path.isabs(a.file) else os.path.join(ROOT, a.file)
    res = {"file": os.path.relpath(src, ROOT), "outputs": [], "rlc": {},
           "v_stats": {}, "state_seq": [], "errors": [], "last_error": ""}

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)

    try:
        ms = msc.Multisim()
        c = ms.open(src)
        res["components"] = list(c.components())
        for ref in res["components"]:
            try:
                res["rlc"][ref] = float(c.rlc(ref))
            except Exception as e:
                res["rlc"][ref] = "ERR:%r" % (e,)
        res["outputs"] = list(c.probes(msc.IOType.All))
        res["inputs"] = list(c.inputs(msc.IOType.All))

        for nm in res["outputs"]:
            c.request_output(nm, RATE, NSAMP, method=msc.Interp.Linear)
        c.run(a.sec)
        for _ in range(40):
            res["state_seq"].append(c.state_name)
            got, _to = c.wait(300)
            time.sleep(0.12)
            if got:
                res["state_seq"].append(c.state_name)
                break
            if c.state_name == "stopped":
                break

        for nm in res["outputs"]:
            try:
                arr, _m = c._c.GetOutputData(nm)
                t = [float(x) for x in arr[0]]
                v = [float(x) for x in arr[1]]
                res["v_stats"][nm] = {
                    "n": len(v),
                    "first": v[0] if v else None,
                    "last": v[-1] if v else None,
                    "min": min(v) if v else None,
                    "max": max(v) if v else None,
                    "t_first": t[0] if t else None,
                    "t_last": t[-1] if t else None,
                }
            except Exception as e:
                res["v_stats"][nm] = {"error": repr(e)}
        try:
            res["last_error"] = c.last_error or ""
        except Exception:
            pass
    except Exception as e:
        res["errors"].append(repr(e))
        traceback.print_exc()

    print("file      :", res["file"])
    print("components:", res.get("components"))
    print("outputs   :", res["outputs"])
    print("RLC       :", res["rlc"])
    for nm, st in res["v_stats"].items():
        print("V[%s] : %s" % (nm, st))
    print("state_seq :", res["state_seq"])
    print("last_error:", res["last_error"])
    if res["errors"]:
        print("errors    :", res["errors"])
    if a.json:
        p = a.json if os.path.isabs(a.json) else os.path.join(ROOT, a.json)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("json      :", os.path.relpath(p, ROOT))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
