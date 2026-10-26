# -*- coding: utf-8 -*-
"""P15 深诊断：仿真到底有没有跑起来。一文件一进程。

对每个文件打印：
  打开后 state / run 前后 state / WaitForNextOutput 每次返回 / last_error 每一步
  另外试一次 "run 更长时间 + 不请求采样" 的对照，判断是不是输出请求本身导致秒停

用法：runtime\\py32\\python.exe tools\\p15_diag.py out/p15_div3.ms14
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p15_div3.ms14")
    src = src if os.path.isabs(src) else os.path.join(ROOT, src)
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)

    ms = msc.Multisim()
    c = ms.open(src)
    print("file       :", os.path.relpath(src, ROOT))
    print("components :", c.components())
    print("outputs    :", c.probes(msc.IOType.All))
    print("inputs     :", c.inputs(msc.IOType.All))
    print("state@open :", c.state_name, "| last_error:", c.last_error)
    print()

    outs = list(c.probes(msc.IOType.All))
    if not outs:
        print("没有探针，退出")
        sys.stdout.flush()
        os._exit(0)
    nm = outs[0]

    print("--- 阶段1：不请求采样，直接 run 1ms ---")
    print("  before:", c.state_name)
    try:
        c.run(0.001)
    except Exception as e:
        print("  run 抛异常:", repr(e))
    time.sleep(0.5)
    print("  after :", c.state_name, "| last_error:", c.last_error)
    try:
        c.stop()
    except Exception as e:
        print("  stop 抛异常:", repr(e))
    time.sleep(0.3)
    print("  after stop:", c.state_name)
    print()

    print("--- 阶段2：请求采样后 run 1ms ---")
    try:
        c.request_output(nm, 2e6, 2000, method=msc.Interp.Linear)
        print("  request_output ok")
    except Exception as e:
        print("  request_output 抛异常:", repr(e))
    print("  before:", c.state_name)
    c.run(0.001)
    print("  right after run:", c.state_name, "| last_error:", c.last_error)
    for i in range(12):
        st = c.state_name
        got, to = c.wait(300)
        print("  poll %-2d state=%-8s got=%-20r timeout=%s err=%r"
              % (i, st, got, to, c.last_error))
        if got:
            break
        if st == "stopped" and i >= 1:
            break
        time.sleep(0.1)
    print("  final state:", c.state_name)
    print()

    print("--- 阶段3：读数据 ---")
    try:
        arr, m = c._c.GetOutputData(nm)
        t = [float(x) for x in arr[0]]
        v = [float(x) for x in arr[1]]
        print("  n=%d t=[%g..%g] v=[%g..%g] first=%g last=%g"
              % (len(v), t[0], t[-1], min(v), max(v), v[0], v[-1]))
        print("  前 5 个点:", [(round(t[i], 9), round(v[i], 6)) for i in range(min(5, len(v)))])
        print("  后 5 个点:", [(round(t[i], 9), round(v[i], 6))
                          for i in range(max(0, len(v) - 5), len(v))])
    except Exception as e:
        print("  GetOutputData 失败:", repr(e), "| last_error:", c.last_error)

    print()
    print("--- 阶段4：RLC 读数 ---")
    for ref in c.components():
        try:
            print("  %-4s = %s" % (ref, c.rlc(ref)))
        except Exception as e:
            print("  %-4s 读不到 (%s)" % (ref, str(e)[:60]))

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
