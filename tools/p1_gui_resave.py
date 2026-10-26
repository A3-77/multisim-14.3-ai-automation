# -*- coding: utf-8 -*-
"""让 Multisim 自己重写 p1_with_probe.ms14（GUI 打开 -> Ctrl+S -> 关闭），
然后用 COM 测保存后的文件。用于定位"COM 不认克隆探针"的原因。

若保存后 COM 能枚举到 -> diff 原文件与保存文件即可找到缺失结构。
若仍然不能 -> 说明 Multisim 内部也没把这个探针注册成 output。
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402

SRC = os.path.join(ROOT, "out", "p1_with_probe.ms14")
WORK = os.path.join(ROOT, "out", "p1_gui_saved.ms14")

shutil.copy(SRC, WORK)
before = os.path.getsize(WORK)
print("工作副本 %s（%d 字节）" % (WORK, before))

msui.kill()
time.sleep(1.5)
h = msui.launch(WORK)
print("hwnd", h)
msui.shot(h, "p1_guisave_before.png")

# 点画布空白处拿焦点，再 Ctrl+S
G.click(300, 300)
time.sleep(0.5)
G.foreground(h)
time.sleep(0.3)
G.hotkey("ctrl", "s")
time.sleep(2.5)
n = msui.dismiss_all()
print("保存时弹窗:", n)
msui.shot(h, "p1_guisave_after.png")

# 关掉 Multisim（可能再弹"是否保存"）
time.sleep(1.0)
msui.kill()
time.sleep(1.5)

after = os.path.getsize(WORK)
print("保存后大小: %d -> %d 字节（%s）" % (before, after,
                                      "变了" if after != before else "没变"))
print("mtime:", time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(WORK))))
