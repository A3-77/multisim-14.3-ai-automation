# -*- coding: utf-8 -*-
"""批量试探：在指定坐标放探针并保存，最后由文件里有没有 CiProbeComp 判定。

用法：python tools/try_probe.py
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msui
import guiauto as G

SRC = os.path.join(ROOT, "out", "acceptance.ms14")
CASES = [
    ("probe_a", (720, 87), (740, 506)),
    ("probe_b", (720, 87), (592, 405)),
    ("probe_c", (900, 108), (740, 506)),
]


def run(name, btn, wire):
    dst = os.path.join(ROOT, "out", name + ".ms14")
    shutil.copy(SRC, dst)
    h = msui.launch(dst)
    G.click(*btn)
    time.sleep(0.8)
    G.click(*wire)
    time.sleep(1.0)
    G.foreground(h)
    G.hotkey("ctrl", "s")
    time.sleep(1.2)
    msui.dismiss_all()
    G.screenshot_screen(os.path.join(ROOT, "out", "shots", name + ".png"))
    print(name, "done", flush=True)


for name, b, w in CASES:
    try:
        run(name, b, w)
    except Exception as e:
        print(name, "FAIL", e, flush=True)
    msui.kill()
    time.sleep(1)
