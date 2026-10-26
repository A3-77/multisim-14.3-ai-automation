# -*- coding: utf-8 -*-
"""P17 一次性流程：杀进程 -> 打开 -> 点"仿真"菜单 -> 截图。

不做 dismiss_all（它会把菜单一起关掉）。

用法：runtime\\py32\\python.exe tools\\p17_all.py
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402

SRC = os.path.join(ROOT, "out", "p15_div3.ms14")


def main():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3.0)

    h = msui.launch(SRC, wait=9.0)
    print("hwnd", h)
    G.screenshot(h, os.path.join(ROOT, "out", "shots", "p17_a_open.png"))

    # 点"仿真(S)"菜单
    G.foreground(h)
    time.sleep(0.5)
    msui.click_img(h, 128, 31, settle=1.5)
    G.screenshot(h, os.path.join(ROOT, "out", "shots", "p17_b_menu.png"))
    print("menu shot ok")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
