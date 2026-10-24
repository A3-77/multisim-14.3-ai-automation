# -*- coding: utf-8 -*-
"""P11 单文件仿真探针：一文件一进程，跑前 taskkill multisim。

用法：runtime\\py32\\python.exe tools\\p11_run.py <ms14> <out.json> [label]
记录：outputs / state_seq / ever_running / V 统计 / 元件值 / 错误原文。
"""
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

SRC = sys.argv[1]
OUT = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(SRC)


def kill_multisim():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)


def stats(vals):
    if not vals:
        return {"n": 0, "min": None, "max": None, "last": None}
    return {"n": len(vals), "min": float(min(vals)), "max": float(max(vals)),
            "last": float(vals[-1])}


def main():
    kill_multisim()
    res = {"label": LABEL, "file": os.path.relpath(SRC, ROOT),
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "components": [], "outputs": [], "rlc": {},
           "state_seq": [], "ever_running": False,
           "transient_seconds": 0.01, "v_stats": {}, "csv": None,
           "last_error": "", "app_last_error": "", "errors": [], "pass": False}

    def note(st):
        res["state_seq"].append(st)
        if st == "running":
            res["ever_running"] = True

    try:
        ms = msc.Multisim()
    except Exception as e:
        res["errors"].append("Connect 失败：%r" % (e,))
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("Connect 失败", repr(e))
        os._exit(1)

    try:
        c = ms.open(SRC)
        print("打开:", c)
        note(c.state_name)
        res["components"] = list(c.components())
        for ref in ("V1", "V2", "R1", "C1"):
            if ref in res["components"]:
                try:
                    res["rlc"][ref] = float(c.rlc(ref))
                except Exception as e:
                    res["errors"].append("RLCValue(%s): %r" % (ref, e))
        print("RLC:", res["rlc"])

        res["outputs"] = list(c.probes(msc.IOType.All))
        print("EnumOutputs:", res["outputs"])
        if not res["outputs"]:
            res["errors"].append("EnumOutputs 为空")

        if res["outputs"]:
            nm = res["outputs"][0]
            try:
                c.request_output(nm, 10000.0, 1000, method=msc.Interp.Linear)
                c.run(0.01)
                for _ in range(30):
                    note(c.state_name)
                    got, to = c.wait(300)
                    time.sleep(0.15)
                    if got:
                        note(c.state_name)
                        break
                    if c.state_name == "stopped":
                        break
                note(c.state_name)
                arr, m = c._c.GetOutputData(nm)
                t, v = list(arr[0]), list(arr[1])
                res["v_stats"][nm] = stats(v)
                res["csv"] = "out/p11_wave_%s.csv" % LABEL
                msc.Circuit.export_csv(os.path.join(ROOT, res["csv"]), {nm: (t, v)})
                print("V:", res["v_stats"][nm])
            except Exception as e:
                res["errors"].append("transient: %r" % (e,))
                print("transient 失败:", repr(e))
                traceback.print_exc()
                try:
                    res["last_error"] = c.last_error
                except Exception:
                    pass
        try:
            res["last_error"] = res["last_error"] or c.last_error
            res["app_last_error"] = ms.last_error
        except Exception:
            pass
        note(c.state_name)
    except Exception as e:
        res["errors"].append("主流程：%r" % (e,))
        print("主流程异常:", repr(e))
        traceback.print_exc()

    v_ok = any(s["n"] and abs(s["min"] - 5.0) < 1e-6 and abs(s["max"] - 5.0) < 1e-6
               and abs(s["last"] - 5.0) < 1e-6 for s in res["v_stats"].values())
    r1 = res["rlc"].get("R1")
    res["pass"] = bool(res["outputs"]) and v_ok and r1 is not None and abs(r1 - 1000.0) < 1e-6
    print("判定: outputs=%s ever_running=%s V5=%s R1=%s => %s"
          % (bool(res["outputs"]), res["ever_running"], v_ok, r1,
             "通过" if res["pass"] else "失败"))
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("已写入", OUT)
    os._exit(0)


if __name__ == "__main__":
    main()
