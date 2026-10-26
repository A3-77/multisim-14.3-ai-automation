# -*- coding: utf-8 -*-
"""用 GUI 打开指定 ms14，截图，看 Multisim 是否接受/报错。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402

src = sys.argv[1]
tag = sys.argv[2] if len(sys.argv) > 2 else "gui"

msui.kill()
time.sleep(1.5)
h = msui.launch(src)
print("hwnd", h, "rect", G.rect(h))
p = msui.shot(h, "%s_open.png" % tag)
print("shot ->", p)
# 再等一会儿看有没有延迟弹窗
time.sleep(2.0)
n = msui.dismiss_all()
print("dialogs dismissed:", n)
p2 = msui.shot(h, "%s_open2.png" % tag)
print("shot2 ->", p2)
msui.kill()
