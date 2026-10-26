# -*- coding: utf-8 -*-
"""P17 最终版：杀进程 -> 打开 -> 点运行(修正缩放) -> 等 -> 截图。

用法：runtime\\py32\\python.exe tools\\p17_final.py
产物：out/shots/p17_gui_run.png（最终读数截图）
"""
import json
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
SHOTS = os.path.join(ROOT, "out", "shots")


def main():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3.0)

    h = msui.launch(SRC, wait=10.0)
    l, t, r, b = G.rect(h)
    win_w = r - l
    print("hwnd", h, "rect", (l, t, r, b), "win_w", win_w)

    G.screenshot(h, os.path.join(SHOTS, "p17_e_open.png"))

    # 截图实际宽度
    import struct
    shot = os.path.join(SHOTS, "p17_e_open.png")
    with open(shot, "rb") as f:
        f.read(16)
        sw, sh = struct.unpack(">II", f.read(8))
    scale = float(win_w) / float(sw)
    print("shot %dx%d  scale %.4f" % (sw, sh, scale))

    def click_shot(sx, sy, settle=1.2):
        x = int(l + sx * scale)
        y = int(t + sy * scale)
        G.foreground(h)
        time.sleep(0.25)
        G.click(x, y)
        time.sleep(settle)
        return x, y

    # 运行按钮：截图 (418,86)
    print("click play:", click_shot(418, 86, settle=2.0))
    G.screenshot(h, os.path.join(SHOTS, "p17_f_play.png"))

    time.sleep(6.0)
    G.screenshot(h, os.path.join(SHOTS, "p17_g_run6s.png"))
    G.screenshot_screen(os.path.join(SHOTS, "p17_h_screen.png"))

    # 最终读数截图
    G.screenshot(h, os.path.join(SHOTS, "p17_gui_run.png"))
    print("done")

    json.dump({"probe_value": None,
               "screenshot": "out/shots/p17_gui_run.png",
               "note": "见 p17_f_play.png / p17_g_run6s.png"},
              open(os.path.join(ROOT, "out", "p17_gui.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
