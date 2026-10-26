# -*- coding: utf-8 -*-
"""P17 续3：修正点击坐标（截图与窗口有 1543/1088≈1.418 的缩放）。

之前 msui.click_img 把截图坐标当窗口坐标，导致点偏 —— 这也解释了
"点运行却弹 20 个对话框"（点到别的工具栏按钮了）。

用法：runtime\\py32\\python.exe tools\\p17_click.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402

SCALE = 1543.0 / 1088.0     # 窗口宽 / 截图宽


def find_hwnd():
    cand = [w for w in G.enum_windows()
            if "multisim" in w["title"].lower() and "[" in w["title"]]
    return cand[0]["hwnd"] if cand else None


def click_shot(h, sx, sy, settle=1.0):
    """按截图坐标点击（自动乘缩放）。"""
    l, t, _, _ = G.rect(h)
    x = int(l + sx * SCALE)
    y = int(t + sy * SCALE)
    G.foreground(h)
    time.sleep(0.2)
    G.click(x, y)
    time.sleep(settle)
    return x, y


def main():
    h = find_hwnd()
    if h is None:
        print("没开着")
        os._exit(1)
    print("hwnd", h, "rect", G.rect(h), "scale", round(SCALE, 4))

    # 运行按钮：截图 (418,86)
    x, y = click_shot(h, 418, 86, settle=1.5)
    print("clicked play at", (x, y))
    G.screenshot(h, os.path.join(ROOT, "out", "shots", "p17_c_play.png"))

    # 等仿真跑
    time.sleep(6.0)
    G.screenshot(h, os.path.join(ROOT, "out", "shots", "p17_d_run6s.png"))
    print("shots ok")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
