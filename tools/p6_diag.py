# -*- coding: utf-8 -*-
"""P6 诊断 harness：打开电路 → EnumOutputs → RunSimulation → 记录 state/错误。

用法：runtime\py32\python.exe tools\p6_diag.py <ms14文件> <输出json>
每个文件单独起一个进程（COM 不稳）。跑前先 taskkill /F /IM multisim.exe。

判定核心：RunSimulation(5.0) 之后 state 是 running 还是 stopped。
stopped = 仿真引擎拒绝了这个电路。
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


def poll_state(c, seconds=2.5):
    """轮询仿真状态，返回 (状态序列, 最终状态)。"""
    seq = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            seq.append(c.state_name)
        except Exception as e:
            seq.append("ERR:%r" % (e,))
        time.sleep(0.25)
    return seq, (seq[-1] if seq else "?")


def main():
    src = sys.argv[1]
    dst = sys.argv[2]
    do_dc = "--dc" in sys.argv

    res = {
        "file": os.path.relpath(src, ROOT),
        "python_bits": 32,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "open_ok": False,
        "multisim_version": None,
        "components": [],
        "outputs_all": [],
        "state_before": None,
        "run_called": False,
        "state_seq": [],
        "state_after_run": None,
        "ever_running": None,
        "last_error": "",
        "netlist_ok": None,
        "netlist_head": None,
        "dc": {},
        "dc_error": None,
        "errors": [],
    }

    print("=" * 66)
    print("P6 诊断：%s" % src)
    print("=" * 66)

    try:
        ms = msc.Multisim()
        res["multisim_version"] = ms.version
        print("Multisim : %s" % ms.version)
    except Exception as e:
        res["errors"].append("Connect 失败：%r" % (e,))
        print("Connect 失败：%r" % (e,))
        json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 1

    try:
        c = ms.open(src)
        res["open_ok"] = True
        print("打开     : %s" % c)

        try:
            res["components"] = list(c.components())
            print("元件     : %s" % res["components"])
        except Exception as e:
            res["errors"].append("EnumComponents: %r" % (e,))

        try:
            res["outputs_all"] = list(c.probes(msc.IOType.All))
            print("EnumOutputs: %s" % res["outputs_all"])
        except Exception as e:
            res["errors"].append("EnumOutputs: %r" % (e,))

        try:
            res["state_before"] = c.state_name
            print("状态(前) : %s" % res["state_before"])
        except Exception as e:
            res["errors"].append("state: %r" % (e,))

        # ---- 网表（结构健全性旁证）----
        try:
            nl = c.netlist()
            res["netlist_ok"] = bool(nl and nl.strip())
            res["netlist_head"] = "\n".join(nl.splitlines()[:25])
            print("网表     : %s" % ("OK" if res["netlist_ok"] else "空"))
        except Exception as e:
            res["errors"].append("ReportNetlist: %r" % (e,))

        # ---- 跑仿真 ----
        print("\n--- RunSimulation(5.0) ---")
        try:
            c.run(5.0)
            res["run_called"] = True
        except Exception as e:
            res["errors"].append("RunSimulation: %r" % (e,))
            print("RunSimulation 异常：%r" % (e,))

        seq, final = poll_state(c)
        res["state_seq"] = seq
        res["state_after_run"] = final
        res["ever_running"] = "running" in seq or "paused" in seq
        print("状态序列 : %s" % seq)
        print("最终状态 : %s   曾运行: %s" % (final, res["ever_running"]))

        try:
            res["last_error"] = c.last_error or ""
            print("LastError: %r" % res["last_error"])
        except Exception as e:
            res["errors"].append("last_error: %r" % (e,))

        # ---- 如果曾运行，做 dc_op（电路能被引擎接受的前提下才有意义）----
        if res["ever_running"]:
            try:
                c.stop()
            except Exception:
                pass
            if do_dc and res["outputs_all"]:
                print("\n--- dc_op ---")
                try:
                    data = c.dc_op(res["outputs_all"])
                    for k, (t, v) in data.items():
                        res["dc"][k] = float(v[-1]) if v else None
                        print("  %s = %.6g" % (k, v[-1] if v else float("nan")))
                except Exception as e:
                    res["dc_error"] = "%s" % (e,)
                    print("  dc_op 失败：%s" % (e,))

    except Exception as e:
        res["errors"].append("主流程：%r" % (e,))
        print("主流程异常：%r" % (e,))
        traceback.print_exc()

    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n已写入 %s" % dst)
    os._exit(0)   # 不调 Disconnect：实测会 segfault


if __name__ == "__main__":
    main()
