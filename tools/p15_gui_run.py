# -*- coding: utf-8 -*-
"""GUI 里真的点一次"运行"，看 Multisim 是否弹错。

COM 的 RunSimulation 可能没真正触发仿真（state 一直是 stopped、last_error 为空）。
GUI 点运行按钮会走完整流程，有错误就会弹窗。

用法：runtime\\py32\\python.exe tools/p15_gui_run.py out/p15_div3r.ms14
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p15_div3r.ms14")
src = src if os.path.isabs(src) else os.path.join(ROOT, src)
tag = sys.argv[2] if len(sys.argv) > 2 else "run"

msui.kill()
time.sleep(1.5)
h = msui.launch(src)
print("hwnd", h, "rect", G.rect(h))
msui.shot(h, "%s_00_open.png" % tag)

# 工具栏"运行"按钮（截图实测坐标，窗口客户区左上为基准）
# 绿色三角约在 (418, 86)，窗口左上 (-7,-7)
G.click(h, 418, 86)
print("clicked run")
time.sleep(1.0)
msui.shot(h, "%s_01_run.png" % tag)

n = msui.dismiss_all()
print("dialogs dismissed:", n)
time.sleep(1.5)
msui.shot(h, "%s_02_after.png" % tag)

# 再看一次有没有弹窗
n2 = msui.dismiss_all()
print("dialogs dismissed 2:", n2)
msui.shot(h, "%s_03_final.png" % tag)

print("shots ->", os.path.join(ROOT, "out", "shots"))
msui.kill()
