# -*- coding: utf-8 -*-
"""诊断 GetOutputData「输出未找到」：逐步跑 COM 调用，定位数据读取断点。

用法：runtime\py32\python.exe tools\diag_read.py [ms14文件]
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

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "ref", "acceptance.ms14")


def main():
    ms = msc.Multisim()
    print("版本:", ms.version)
    c = ms.open(SRC)
    print("打开:", c)

    outs = list(c.probes(msc.IOType.All))
    print("EnumOutputs:", outs)
    for o in outs:
        print("  repr:", repr(o), "len:", len(o))
    if not outs:
        print("没有输出，退出")
        os._exit(1)
    name = outs[0]

    # ---- 路径 A：transient + Raw ----
    print("\n=== A: SetOutputRequest(Raw) + RunSimulation(0.01) ===")
    try:
        c.request_output(name, 10000.0, 1000, method=msc.Interp.Raw, repeat=False)
        print("SetOutputRequest OK")
    except Exception as e:
        print("SetOutputRequest 失败:", repr(e))
    try:
        c.run(0.01)
        print("RunSimulation 已调用")
    except Exception as e:
        print("RunSimulation 失败:", repr(e))
    t0 = time.time()
    seq = []
    while time.time() - t0 < 3.0:
        try:
            seq.append(c.state_name)
        except Exception as e:
            seq.append("ERR")
        time.sleep(0.2)
    print("state_seq:", seq)
    try:
        got, to = c.wait(2000)
        print("WaitForNextOutput:", got, "timed_out:", to)
    except Exception as e:
        print("WaitForNextOutput 失败:", repr(e))
    try:
        t, v = c.read(name)
        print("GetOutputData OK: n=%d last=%s" % (len(v), v[-3:] if v else v))
    except Exception as e:
        print("GetOutputData 失败:", repr(e))
        print("LastError:", repr(c.last_error))

    # ---- 路径 B：dc_op ----
    print("\n=== B: DoDCOperatingPoint ===")
    try:
        c._c.DoDCOperatingPoint(msc._bstr_array([name]))
        print("DoDCOperatingPoint 已调用")
        got, to = c.wait(3000)
        print("WaitForNextOutput:", got, "timed_out:", to)
        t, v = c.read(name)
        print("GetOutputData OK: n=%d vals=%s" % (len(v), v[:5]))
    except Exception as e:
        print("dc_op 路径失败:", repr(e))
        print("LastError:", repr(c.last_error))

    # ---- 路径 C：RunSimulationUntilNextOutput ----
    print("\n=== C: RunSimulationUntilNextOutput ===")
    try:
        c.run_until_next_output()
        print("已调用")
        got, to = c.wait(3000)
        print("WaitForNextOutput:", got, "timed_out:", to)
        t, v = c.read(name)
        print("GetOutputData OK: n=%d vals=%s" % (len(v), v[:5]))
    except Exception as e:
        print("路径 C 失败:", repr(e))
        print("LastError:", repr(c.last_error))

    # ---- 名字变体 ----
    print("\n=== D: 名字变体 ===")
    for variant in (name, msc._fix(name), name.replace("(", "（").replace(")", "）")):
        try:
            t, v = c.read(variant)
            print("read(%r) OK n=%d" % (variant, len(v)))
            break
        except Exception as e:
            print("read(%r) 失败: %s" % (variant, repr(e)[:80]))

    print("\n完成")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
