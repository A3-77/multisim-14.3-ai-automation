# -*- coding: utf-8 -*-
"""P14：枚举 Multisim COM 对象的方法，找有没有能直接拿 SPICE 网表的接口。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(os.path.join(ROOT, "out", "p13_a3.ms14"))

for label, obj in (("APP", ms._app), ("CIRCUIT", c._c)):
    print("=" * 60)
    print(label)
    print("=" * 60)
    try:
        names = sorted(obj._oleobj_.GetTypeInfo().GetIDsOfNames(
            *[u for u in obj._oleobj_.GetTypeInfo().GetDocumentation(-1)[0:1]]))
    except Exception:
        names = None
    # 直接遍历类型库
    try:
        ti = obj._oleobj_.GetTypeInfo()
        n = ti.GetTypeAttr().cFuncs
        out = []
        for i in range(n):
            fd = ti.GetFuncDesc(i)
            nm = ti.GetNames(fd.memid)[0]
            out.append(nm)
        print("方法 %d 个:" % len(out))
        for nm in sorted(set(out)):
            print("  ", nm)
    except Exception as e:
        print("类型库读取失败:", repr(e))

sys.stdout.flush()
os._exit(0)
