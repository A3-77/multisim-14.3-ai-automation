# -*- coding: utf-8 -*-
"""P12：RC 低通 COM 验证（一文件一进程，跑前 taskkill multisim）。

用法：runtime\\py32\\python.exe tools\\p12_validate.py
产物：out/ref/p12_rc.json、out/ref/rc_lowpass_wave.csv
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

SRC = os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14")
JSON_OUT = os.path.join(ROOT, "out", "ref", "p12_rc.json")
CSV_OUT = os.path.join(ROOT, "out", "ref", "rc_lowpass_wave.csv")

SEC = 0.001          # 瞬态 1ms
NSAMP = 2000         # 采样 2000 点
RATE = NSAMP / SEC   # 2e6
TAU = 100e-6         # R*C = 1k * 100nF


def kill_multisim():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)


def main():
    kill_multisim()
    res = {"file": os.path.relpath(SRC, ROOT),
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "open_ok": False, "multisim_version": None,
           "components": [], "outputs": [], "rlc": {},
           "transient": {"seconds": SEC, "requested_samples": NSAMP, "sample_rate": RATE},
           "v_stats": {}, "state_seq": [], "ever_running": False,
           "tau_measured_s": None, "monotonic_ratio": None,
           "csv": None, "last_error": "", "errors": [], "pass": False}

    def note(st):
        res["state_seq"].append(st)
        if st == "running":
            res["ever_running"] = True

    try:
        ms = msc.Multisim()
        res["multisim_version"] = ms.version
    except Exception as e:
        res["errors"].append("Connect 失败：%r" % (e,))
        json.dump(res, open(JSON_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("Connect 失败", repr(e))
        os._exit(1)

    try:
        c = ms.open(SRC)
        res["open_ok"] = True
        note(c.state_name)
        res["components"] = list(c.components())
        for ref in ("R1", "C1"):
            try:
                res["rlc"][ref] = float(c.rlc(ref))
            except Exception as e:
                res["errors"].append("RLCValue(%s): %r" % (ref, e))

        res["outputs"] = list(c.probes(msc.IOType.All))
        if not res["outputs"]:
            res["errors"].append("EnumOutputs 为空")

        if res["outputs"]:
            nm = res["outputs"][0]
            c.request_output(nm, RATE, NSAMP, method=msc.Interp.Linear)
            c.run(SEC)
            for _ in range(40):
                note(c.state_name)
                got, _to = c.wait(300)
                time.sleep(0.12)
                if got:
                    note(c.state_name)
                    break
                if c.state_name == "stopped":
                    break
            note(c.state_name)

            arr, _m = c._c.GetOutputData(nm)
            t = [float(x) for x in arr[0]]
            v = [float(x) for x in arr[1]]
            st = {"n": len(v),
                  "first": v[0] if v else None,
                  "last": v[-1] if v else None,
                  "min": min(v) if v else None,
                  "max": max(v) if v else None,
                  "t_first": t[0] if t else None,
                  "t_last": t[-1] if t else None}
            res["v_stats"][nm] = st

            # 曲线形状判定
            if len(v) > 2:
                steps = sum(1 for i in range(1, len(v)) if v[i] < v[i - 1] - 1e-9)
                res["monotonic_ratio"] = 1.0 - steps / float(len(v) - 1)
                target = v[0] + 0.632 * (v[-1] - v[0])
                for i in range(1, len(v)):
                    if v[i] >= target:
                        res["tau_measured_s"] = t[i]
                        break

            msc.Circuit.export_csv(CSV_OUT, {nm: (t, v)})
            res["csv"] = os.path.relpath(CSV_OUT, ROOT)

        try:
            res["last_error"] = c.last_error or ""
        except Exception:
            pass
    except Exception as e:
        res["errors"].append("主流程：%r" % (e,))
        traceback.print_exc()

    # ---- 判定 ----
    st = next(iter(res["v_stats"].values()), None)
    curve_ok = bool(st and st["n"] >= 100 and st["first"] is not None
                    and st["first"] < 0.2 and abs(st["last"] - 1.0) < 0.01
                    and st["max"] <= 1.05 and st["min"] >= -0.05
                    and (res["monotonic_ratio"] or 0) > 0.98)
    tau_ok = res["tau_measured_s"] is not None and \
        0.5 * TAU < res["tau_measured_s"] < 2.0 * TAU
    r_ok = abs((res["rlc"].get("R1") or 0) - 1000.0) < 1e-6
    c_ok = abs((res["rlc"].get("C1") or 0) - 1e-7) < 1e-15
    res["checks"] = {"outputs_nonempty": bool(res["outputs"]),
                     "rc_charge_curve": curve_ok, "tau_near_100us": tau_ok,
                     "R1_1000": r_ok, "C1_1e-7": c_ok}
    res["pass"] = bool(res["open_ok"] and res["outputs"] and curve_ok and r_ok and c_ok)

    print("outputs   :", res["outputs"])
    print("RLC       :", res["rlc"])
    print("V 统计    :", st)
    print("tau 实测  : %s s（理论 100µs）" % res["tau_measured_s"])
    print("单调比    :", res["monotonic_ratio"])
    print("state_seq :", res["state_seq"])
    print("checks    :", res["checks"])
    print("判定      :", "通过" if res["pass"] else "失败")
    json.dump(res, open(JSON_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
