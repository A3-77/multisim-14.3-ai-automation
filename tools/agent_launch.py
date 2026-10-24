# -*- coding: utf-8 -*-
"""启动常驻提权代理（只弹一次 UAC）。"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
AGENT = os.path.join(HERE, "elev_agent.py")

r = ctypes.windll.shell32.ShellExecuteW(
    None, "runas", PY, '-u "%s"' % AGENT, ROOT, 0)
print("ShellExecuteW ->", r, "(<=32 表示失败)")
