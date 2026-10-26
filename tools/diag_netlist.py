# -*- coding: utf-8 -*-
"""对比两个 ms14 文件的 COM 网表 + 仿真输出行为。
用法：runtime\py32\python.exe tools\diag_netlist.py <文件1> <文件2>
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402


def diag(path):
    ms = msc.Multisim()
    print("版本:", ms.version)
    c = ms.open(path)
    print("打开:", c)
    outs = list(c.probes(msc.IOType.All))
    print("EnumOutputs:", outs)
    try:
        nl = c.netlist()
        print("--- 网表 ---")
        print(nl)
    except Exception as e:
        print("网表失败:", repr(e))
    if outs:
        name = outs[0]
        try:
            c.request_output(name, 10000.0, 1000, method=msc.Interp.Raw)
            c.run(0.01)
            t0 = time.time()
            seq = []
            while time.time() - t0 < 2.0:
                seq.append(c.state_name)
                time.sleep(0.15)
            print("state_seq:", seq)
            got, to = c.wait(2000)
            print("WaitForNextOutput:", got, "timed_out:", to)
            t, v = c.read(name)
            print("GetOutputData: n=%d first=%s last=%s" % (len(v), v[:3], v[-3:]))
        except Exception as e:
            print("读数失败:", repr(e), "| LastError:", repr(c.last_error))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    diag(sys.argv[1])
