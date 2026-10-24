# -*- coding: utf-8 -*-
"""一次性提权运行器：把某个脚本以管理员身份跑一遍，等它写出结果文件。

用法：python tools/oneshot.py tools/exp1.py out/exp1.json
会弹一次 UAC。跑完自动退出。
"""
import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
PYW = os.path.join(ROOT, "runtime", "py32", "pythonw.exe")
if not os.path.exists(PYW):
    PYW = PY

script = os.path.abspath(sys.argv[1])
sentinel = os.path.join(ROOT, sys.argv[2]) if len(sys.argv) > 2 else None
extra = " ".join('"%s"' % a for a in sys.argv[3:])
outlog = os.path.join(ROOT, "out", "oneshot.out")

if sentinel and os.path.exists(sentinel):
    os.remove(sentinel)

# 用 cmd 包一层，把 stdout/stderr 也留下来
cmdline = '/c ""%s" -u "%s" %s > "%s" 2>&1"' % (PY, script, extra, outlog)
r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", cmdline, ROOT, 0)
print("ShellExecuteW ->", r, "(<=32 失败)")
if r <= 32:
    sys.exit(1)

t0 = time.time()
while time.time() - t0 < 240:
    if sentinel and os.path.exists(sentinel):
        print("完成，用时 %.1fs" % (time.time() - t0))
        sys.exit(0)
    time.sleep(1.0)
print("超时")
sys.exit(2)
