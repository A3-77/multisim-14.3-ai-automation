# -*- coding: utf-8 -*-
"""验收电路 COM 验证：EnumOutputs → 瞬态 → V 统计 → 导出。

用法：
    runtime\\py32\\python.exe tools/validate_acceptance.py [ms14] [label] [期望电压]
默认验证 out/ref/acceptance.ms14，标签 source，期望 5.0V。
分压器版本：
    ... tools/validate_acceptance.py out/ref/acceptance_divider.ms14 divider 2.5

产物：
    out/p0_waveform_<label>.csv
    out/p0_validation.json   （多次运行按 label 合并）

要点（都是踩过的坑）：
  * 一文件一进程，跑前 taskkill multisim；退出用 os._exit()（Disconnect 会 segfault）
  * **必须在 stop() 之前读数据**：部分电路 stop 后 GetOutputData 报「未指定的错误」
  * 判定不只看均值，还要看极差（span）——恒压才算稳态
"""
import csv
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "ref", "acceptance.ms14")
LABEL = sys.argv[2] if len(sys.argv) > 2 else "source"
EXPECT = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
SECS = 0.01
SR = 200000.0
TOL = 1e-3
JSON_OUT = os.path.join(ROOT, "out", "p0_validation.json")


def stats(vals):
    if not vals:
        return {"n": 0}
    lo, hi = float(min(vals)), float(max(vals))
    return {"n": len(vals), "min": lo, "max": hi, "span": hi - lo,
            "first": float(vals[0]), "last": float(vals[-1]),
            "mean": float(sum(vals) / len(vals))}


def main():
    res = {
        "label": LABEL,
        "file": os.path.relpath(SRC, ROOT),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "expect_v": EXPECT,
        "transient_seconds": SECS,
        "components": [],
        "outputs": [],
        "rlc": {},
        "v_stats": {},
        "state_after": None,
        "last_error": "",
        "csv": None,
        "checks": {},
        "pass": False,
        "errors": [],
    }

    print("=" * 66)
    print("验收验证 [%s]：%s" % (LABEL, SRC))
    print("=" * 66)

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)

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
        print("打开     : %s" % c)

        try:
            res["components"] = list(c.components())
            print("元件     : %s" % res["components"])
        except Exception as e:
            res["errors"].append("EnumComponents: %r" % (e,))

        for ref in ("R1", "R2", "C1", "V1"):
            try:
                v = c.rlc(ref)
                res["rlc"][ref] = float(v) if v is not None else None
                print("RLCValue(%s) = %s" % (ref, v))
            except Exception as e:
                res["rlc"][ref] = None
                res["errors"].append("RLCValue(%s): %r" % (ref, e))

        try:
            res["outputs"] = list(c.probes(msc.IOType.All))
            print("EnumOutputs: %s" % res["outputs"])
        except Exception as e:
            res["errors"].append("EnumOutputs: %r" % (e,))

        if res["outputs"]:
            print("\n--- transient(%g) ---" % SECS)
            n = int(max(1000, SECS * SR * 1.2))
            for nm in res["outputs"]:
                try:
                    c.request_output(nm, SR, n, method=msc.Interp.Linear)
                except Exception as e:
                    res["errors"].append("request %s: %r" % (nm, e))
            c.run(SECS, pause=False)
            deadline = time.time() + 25.0
            while time.time() < deadline:
                try:
                    got, _ = c.wait(500)
                except Exception as e:
                    res["errors"].append("wait: %r" % (e,))
                    break
                if got:
                    break
                if c.state == msc.SimState.Stopped:
                    break
            time.sleep(0.5)

            # 读数据必须在 stop() 之前
            data = {}
            for nm in res["outputs"]:
                try:
                    data[nm] = c.read(nm)
                except Exception as e:
                    res["errors"].append("read %s: %r" % (nm, e))
            for nm, (t, v) in data.items():
                if not v:
                    continue
                res["v_stats"][nm] = stats(v)
                s = res["v_stats"][nm]
                print("  %-16s n=%-5d min=%.6g max=%.6g span=%.3g last=%.6g"
                      % (nm, s["n"], s["min"], s["max"], s["span"], s["last"]))

            if data:
                csv_out = os.path.join(ROOT, "out", "p0_waveform_%s.csv" % LABEL)
                try:
                    msc.Circuit.export_csv(csv_out, data)
                    res["csv"] = os.path.relpath(csv_out, ROOT)
                    print("波形已导出 %s" % csv_out)
                except Exception as e:
                    res["errors"].append("export_csv: %r" % (e,))

            try:
                c.stop()
            except Exception:
                pass
        else:
            res["errors"].append("EnumOutputs 为空：探针未注册，无法仿真")

        try:
            res["state_after"] = c.state_name
            print("状态(后) : %s" % res["state_after"])
        except Exception:
            pass
        try:
            res["last_error"] = c.last_error or ""
        except Exception:
            pass

    except Exception as e:
        res["errors"].append("主流程：%r" % (e,))
        print("主流程异常：%r" % (e,))
        traceback.print_exc()

    # ---- 判定 ----
    target = None
    for nm, s in res["v_stats"].items():
        if "探针" in nm or target is None:
            target = (nm, s)
            if "探针" in nm:
                break
    v_ok = bool(target) and abs(target[1]["mean"] - EXPECT) <= TOL \
        and target[1]["span"] <= TOL
    r1_ok = res["rlc"].get("R1") is not None and abs(res["rlc"]["R1"] - 1000.0) < 0.5
    res["checks"] = {"v_ok": v_ok, "r1_ok": r1_ok,
                     "v_output": target[0] if target else None,
                     "v_mean": target[1]["mean"] if target else None,
                     "v_span": target[1]["span"] if target else None,
                     "r1": res["rlc"].get("R1")}
    res["pass"] = bool(res["outputs"]) and v_ok and r1_ok
    print("\n判定: V=%.6g（期望 %.3g，极差 %.3g）  R1=%sΩ  =>  %s"
          % (res["checks"]["v_mean"] or 0, EXPECT, res["checks"]["v_span"] or 0,
             res["rlc"].get("R1"), "通过" if res["pass"] else "失败"))

    # ---- 合并写入 ----
    allj = {"runs": {}}
    if os.path.exists(JSON_OUT):
        try:
            with open(JSON_OUT, encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict) and isinstance(old.get("runs"), dict):
                allj = old
        except Exception:
            pass
    allj["runs"][LABEL] = res
    allj["timestamp"] = res["timestamp"]
    allj["all_pass"] = all(r.get("pass") for r in allj["runs"].values())
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(allj, f, ensure_ascii=False, indent=2)
    print("已写入 %s" % JSON_OUT)
    os._exit(0 if res["pass"] else 3)


if __name__ == "__main__":
    main()
