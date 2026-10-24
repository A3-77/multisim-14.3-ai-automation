# -*- coding: utf-8 -*-
"""验收电路 COM 验证：EnumOutputs → transient(0.01) → V 统计 → 导出。

用法：runtime\py32\python.exe tools\validate_acceptance.py [ms14文件]
默认验证 out/ref/acceptance.ms14，产物：
    out/p0_waveform.csv    瞬态波形
    out/p0_validation.json outputs / R1=RLCValue / V 统计 / components / timestamp
一文件一进程，跑前 taskkill multisim；退出用 os._exit(0)（Disconnect 会 segfault）。
"""
import csv
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "ref", "acceptance.ms14")
CSV_OUT = os.path.join(ROOT, "out", "p0_waveform.csv")
JSON_OUT = os.path.join(ROOT, "out", "p0_validation.json")


def stats(vals):
    if not vals:
        return {"min": None, "max": None, "last": None, "n": 0}
    return {"min": float(min(vals)), "max": float(max(vals)),
            "last": float(vals[-1]), "n": len(vals)}


def main():
    res = {
        "file": os.path.relpath(SRC, ROOT),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "open_ok": False,
        "multisim_version": None,
        "components": [],
        "outputs": [],
        "r1_ohm": None,
        "c1_farad": None,
        "v1_volt": None,
        "transient_seconds": 0.01,
        "v_stats": {},
        "state_after": None,
        "last_error": "",
        "csv": None,
        "pass": False,
        "errors": [],
    }

    print("=" * 66)
    print("验收验证：%s" % SRC)
    print("=" * 66)

    try:
        ms = msc.Multisim()
        res["multisim_version"] = ms.version
        print("Multisim : %s" % ms.version)
    except Exception as e:
        res["errors"].append("Connect 失败：%r" % (e,))
        print("Connect 失败：%r" % (e,))
        json.dump(res, open(JSON_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os._exit(1)

    try:
        c = ms.open(SRC)
        res["open_ok"] = True
        print("打开     : %s" % c)

        # ---- 元件 ----
        try:
            res["components"] = list(c.components())
            print("元件     : %s" % res["components"])
        except Exception as e:
            res["errors"].append("EnumComponents: %r" % (e,))

        # ---- RLC 值（COM 实际读到的）----
        for ref, key in (("R1", "r1_ohm"), ("C1", "c1_farad"), ("V1", "v1_volt")):
            try:
                v = c.rlc(ref)
                res[key] = float(v) if v is not None else None
                print("RLCValue(%s) = %s" % (ref, v))
            except Exception as e:
                res["errors"].append("RLCValue(%s): %r" % (ref, e))
                print("RLCValue(%s) 失败：%r" % (ref, e))

        # ---- 探针输出 ----
        try:
            res["outputs"] = list(c.probes(msc.IOType.All))
            print("EnumOutputs: %s" % res["outputs"])
        except Exception as e:
            res["errors"].append("EnumOutputs: %r" % (e,))

        # ---- 瞬态 ----
        if res["outputs"]:
            print("\n--- transient(0.01) ---")
            try:
                data = c.transient(0.01, outputs=res["outputs"])
                for nm, (t, v) in data.items():
                    res["v_stats"][nm] = stats(v)
                    s = res["v_stats"][nm]
                    print("  %-16s n=%-5d min=%.6g max=%.6g last=%.6g"
                          % (nm, s["n"], s["min"] or 0, s["max"] or 0, s["last"] or 0))
                # 导出 CSV
                try:
                    msc.Circuit.export_csv(CSV_OUT, data)
                    res["csv"] = os.path.relpath(CSV_OUT, ROOT)
                    print("波形已导出 %s" % CSV_OUT)
                except Exception as e:
                    res["errors"].append("export_csv: %r" % (e,))
            except Exception as e:
                res["errors"].append("transient: %r" % (e,))
                print("transient 失败：%r" % (e,))
                traceback.print_exc()
        else:
            res["errors"].append("EnumOutputs 为空：探针未注册，无法 transient")

        try:
            res["state_after"] = c.state_name
            print("状态(后) : %s" % res["state_after"])
        except Exception as e:
            res["errors"].append("state: %r" % (e,))
        try:
            res["last_error"] = c.last_error or ""
            print("LastError: %r" % res["last_error"])
        except Exception as e:
            res["errors"].append("last_error: %r" % (e,))

    except Exception as e:
        res["errors"].append("主流程：%r" % (e,))
        print("主流程异常：%r" % (e,))
        traceback.print_exc()

    # ---- 判定 ----
    v_ok = False
    for nm, s in res["v_stats"].items():
        if s["n"] and abs(s["min"] - 5.0) < 1e-6 and abs(s["max"] - 5.0) < 1e-6 \
                and abs(s["last"] - 5.0) < 1e-6:
            v_ok = True
    r1_ok = res["r1_ohm"] is not None and abs(res["r1_ohm"] - 1000.0) < 1e-6
    res["pass"] = bool(res["outputs"]) and v_ok and r1_ok
    print("\n判定: outputs=%s  V恒5.0V=%s  R1=%sΩ  =>  %s"
          % (bool(res["outputs"]), v_ok, res["r1_ohm"], "通过" if res["pass"] else "失败"))

    json.dump(res, open(JSON_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("已写入 %s" % JSON_OUT)
    os._exit(0)


if __name__ == "__main__":
    main()
