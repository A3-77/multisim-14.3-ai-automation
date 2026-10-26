# -*- coding: utf-8 -*-
"""定位：为什么 dc_run.py 读不到、p18_run2.py 读得到？

两者跑的是同一个 v1_dc_r.ms14，唯一区别是**仿真前多调了哪些 COM 方法**。
逐个加，看谁把输出注册搞坏了。

    P0  open -> probes -> request -> run -> wait -> read      （p18 的序列）
    P1  P0 + 再调一次 probes()（EnumOutputs）
    P2  P0 + components()（EnumComponents）
    P3  P0 + rlc("R1")（RLCValue）
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

MS14 = os.path.join(ROOT, "out", "dc", "v1_dc_r.ms14")
OUT = os.path.join(ROOT, "out", "dc", "bisect.json")


def run_case(app, extra=None, label=""):
    circ = app.open(MS14)
    outs = list(circ.probes())
    preamble = []
    try:
        if extra == "probes":
            outs2 = list(circ.probes())
            preamble.append(("probes2", outs2))
        elif extra == "components":
            preamble.append(("components", list(circ.components())))
        elif extra == "rlc":
            preamble.append(("rlc", circ.rlc("R1")))
    except Exception as e:
        preamble.append((extra, "ERR:%s" % e))

    for nm in outs:
        circ.request_output(nm, 200000.0, 1200, method=msc.Interp.Linear)
    circ.run(0.006, pause=False)
    if extra == "probes_after":
        # 关键对照：run 之后、read 之前再枚举一次输出
        time.sleep(0.2)
        preamble.append(("probes_after_run", list(circ.probes())))
    deadline = time.time() + 10.0
    got = ()
    while time.time() < deadline:
        got, _to = circ.wait(500)
        if got:
            break
        if circ.state == msc.SimState.Stopped:
            break
    time.sleep(0.5)
    read = {}
    for nm in outs:
        try:
            t, v = circ.read(nm)
            read[nm] = {"n": len(v), "min": min(v) if v else None,
                        "max": max(v) if v else None}
        except Exception as e:
            read[nm] = {"err": str(e)}
    try:
        circ.stop()
    except Exception:
        pass
    return {"case": label, "preamble": preamble, "state": str(circ.state),
            "got": list(got), "read": read}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="P0")
    args = ap.parse_args()
    table = {"P0": (None, "P0 基线（p18 序列）"),
             "P1": ("probes", "P1 + 二次 EnumOutputs"),
             "P2": ("components", "P2 + EnumComponents"),
             "P3": ("rlc", "P3 + RLCValue"),
             "P4": ("probes_after", "P4 run 后、read 前再 EnumOutputs")}
    extra, label = table[args.case]

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    app = msc.Multisim()
    r = run_case(app, extra, label)
    ok = any("n" in v for v in r["read"].values())
    print("\n%-26s %s" % (label, "读到数据" if ok else "读不到"))
    print("  preamble: %s" % r["preamble"])
    print("  read    : %s" % r["read"])
    sys.stdout.flush()

    path = OUT.replace(".json", "_%s.json" % args.case)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"ms14": MS14, "case": r}, f, ensure_ascii=False, indent=2)
    print("证据 -> %s" % path)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
