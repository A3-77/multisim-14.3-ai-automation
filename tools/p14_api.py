# -*- coding: utf-8 -*-
"""P14g: 枚举 COM 接口方法 + 尝试各种网表导出格式"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p13_a3.ms14")

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)

print("=== circuit COM 对象方法 ===")
try:
    names = sorted(n for n in dir(c._c) if not n.startswith("_"))
    print(", ".join(names))
except Exception as e:
    print("dir 失败", repr(e))

print()
print("=== 尝试 ReportNetlist 各 fmt ===")
for fmt in range(0, 6):
    try:
        r = c._c.ReportNetlist(False, fmt, None)
        s = str(r)
        print("fmt=%d -> len=%d : %s" % (fmt, len(s), s[:300].replace("\n", " | ")))
    except Exception as e:
        print("fmt=%d -> 失败 %r" % (fmt, e))

print()
print("=== 尝试其他可能的导出方法 ===")
for meth in ("ExportNetlist", "ExportSpiceNetlist", "GetNetlist", "ExportToSpice",
             "WriteNetlist", "SaveNetlist", "GetSpiceNetlist"):
    f = getattr(c._c, meth, None)
    if f is None:
        continue
    print("存在方法:", meth)

sys.stdout.flush()
os._exit(0)
