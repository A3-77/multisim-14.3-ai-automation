# -*- coding: utf-8 -*-
"""以管理员身份启动提权助手，并等它就绪。会弹一次 UAC。"""
import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYW = os.path.join(ROOT, "runtime", "py32", "pythonw.exe")
PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
if not os.path.exists(PYW):
    PYW = PY
SCRIPT = os.path.join(HERE, "elev.py")
HB = os.path.join(ROOT, "out", "ehb.txt")
RES = os.path.join(ROOT, "out", "eres.json")

for f in (HB, RES):
    if os.path.exists(f):
        os.remove(f)

r = ctypes.windll.shell32.ShellExecuteW(None, "runas", PYW, '"%s"' % SCRIPT, ROOT, 0)
print("ShellExecuteW ->", r, "(<=32 表示失败；UAC 被拒绝是 5)")
if r <= 32:
    sys.exit(1)

t0 = time.time()
while time.time() - t0 < 60:
    if os.path.exists(HB):
        print("提权助手已就绪，用时 %.1fs" % (time.time() - t0))
        break
    time.sleep(0.5)
else:
    print("等超时：助手没起来（UAC 可能被取消了）")
    sys.exit(2)

# 关键：沙箱会在本进程结束时清掉整棵进程树，所以这里必须一直挂着，
# 提权助手才能活着。用 run_in_background 跑本脚本即可。
print("保持驻留中（不要停这个任务）…", flush=True)
while True:
    time.sleep(5)
