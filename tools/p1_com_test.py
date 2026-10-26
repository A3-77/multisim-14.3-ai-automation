# -*- coding: utf-8 -*-
"""P1：单进程 COM 测试 —— 打开带老式探针的电路，枚举 output 并读数。

用法：runtime\py32\python.exe tools\p1_com_test.py <ms14文件> <输出json>
每个文件单独起一个进程（COM 不稳，连续 open 会 segfault）。
"""
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p1_with_probe.ms14")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "out", "p1_probe_test.json")

    res = {
        "file": os.path.relpath(src, ROOT),
        "python_bits": 32,
        "multisim_version": None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "outputs_all": [],
        "outputs_voltage": [],
        "outputs_current": [],
        "components": [],
        "rlc": {},
        "dc": {},
        "dc_error": None,
        "transient": {},
        "transient_error": None,
        "state_after_run": None,
        "extra_errors": [],
        "probe_xml_summary": None,
    }

    print("=" * 66)
    print("P1 COM 测试：%s" % src)
    print("=" * 66)

    try:
        ms = msc.Multisim()
        res["multisim_version"] = ms.version
        print("Multisim : %s" % ms.version)
    except Exception as e:
        res["dc_error"] = "Connect 失败：%r" % (e,)
        print("Connect 失败：%r" % (e,))
        json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 1

    try:
        c = ms.open(src)
        print("打开     : %s" % c)
        print("状态     : %s" % c.state_name)

        # 枚举 output
        for label, kind in (("All", msc.IOType.All),
                            ("Voltage", msc.IOType.Voltage),
                            ("Current", msc.IOType.Current)):
            try:
                names = list(c.probes(kind))
            except Exception as e:
                names = []
                res["extra_errors"].append("EnumOutputs(%s): %r" % (label, e))
            key = {"All": "outputs_all", "Voltage": "outputs_voltage",
                   "Current": "outputs_current"}[label]
            res[key] = names
            print("EnumOutputs(%-7s) -> %s" % (label + ")", names))

        # 元件值
        try:
            comps = list(c.components())
            res["components"] = comps
            print("元件     : %s" % comps)
            for ref in comps:
                try:
                    v = c.rlc(ref)
                    res["rlc"][ref] = v
                    print("  RLCValue(%s) = %r" % (ref, v))
                except Exception as e:
                    print("  RLCValue(%s) 失败 %r" % (ref, e))
        except Exception as e:
            res["extra_errors"].append("EnumComponents: %r" % (e,))

        outputs = res["outputs_all"]
        if not outputs:
            print("\n！！没有可用 output —— 探针没被 COM 识别")

        # dc_op
        if outputs:
            print("\n--- dc_op ---")
            try:
                data = c.dc_op(outputs)
                for k, (t, v) in data.items():
                    res["dc"][k] = float(v[-1]) if v else None
                    print("  %s = %.6g   (%d 点, 首值 %.6g)"
                          % (k, v[-1] if v else float("nan"), len(v), v[0] if v else 0))
            except Exception as e:
                res["dc_error"] = "%s" % (e,)
                print("  dc_op 失败：%s" % (e,))
                traceback.print_exc()

            # transient 兜底
            print("\n--- transient(0.01) 兜底 ---")
            try:
                data = c.transient(0.01, outputs=outputs, num_samples=2000)
                for k, (t, v) in data.items():
                    if v:
                        res["transient"][k] = {"final": float(v[-1]),
                                               "first": float(v[0]),
                                               "max": float(max(v)),
                                               "min": float(min(v)),
                                               "n": len(v)}
                        print("  %s: n=%d 末值=%.6g 首值=%.6g max=%.6g min=%.6g"
                              % (k, len(v), v[-1], v[0], max(v), min(v)))
            except Exception as e:
                res["transient_error"] = "%s" % (e,)
                print("  transient 失败：%s" % (e,))
                traceback.print_exc()

            try:
                res["state_after_run"] = c.state_name
                print("\n仿真状态 : %s" % c.state_name)
                print("LastError: %s" % (c.last_error or "(空)"))
            except Exception as e:
                res["extra_errors"].append("state: %r" % (e,))

    except Exception as e:
        res["extra_errors"].append("主流程：%r" % (e,))
        print("主流程异常：%r" % (e,))
        traceback.print_exc()

    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n已写入 %s" % dst)
    # 不调 Disconnect：实测会 segfault
    os._exit(0)


if __name__ == "__main__":
    main()
