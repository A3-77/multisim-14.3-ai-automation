# -*- coding: utf-8 -*-
"""P17 续2：点开"仿真(S)"菜单并截图，找真正的"运行"项。

用法：runtime\\py32\\python.exe tools\\p17_menu.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402


def find_hwnd():
    cand = [w for w in G.enum_windows()
            if "multisim" in w["title"].lower() and "[" in w["title"]]
    return cand[0]["hwnd"] if cand else None


def main():
    h = find_hwnd()
    if h is None:
        print("没开着")
        os._exit(1)
    G.foreground(h)
    time.sleep(0.6)

    # 点菜单栏"仿真(S)"（截图坐标约 128,31）
    msui.click_img(h, 128, 31, settle=1.2)
    msui.shot(h, "p17_menu_simulate.png")
    print("shot -> out/shots/p17_menu_simulate.png")

    # 顺便截整屏，菜单可能溢出窗口
    G.screenshot_screen(os.path.join(ROOT, "out", "shots", "p17_menu_screen.png"))
    print("screen -> out/shots/p17_menu_screen.png")

    # 不关菜单，直接退出进程
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
