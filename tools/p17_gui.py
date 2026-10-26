# -*- coding: utf-8 -*-
"""P17：GUI 里跑一次仿真，截图看探针信息框的读数。

判定：GUI 显示 2.5V -> 问题在 COM 读取链路；GUI 也是 0V -> 问题在电路/网表。

用法：runtime\\py32\\python.exe tools\\p17_gui.py
产物：out/shots/p17_gui_run.png
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
SHOT = os.path.join(ROOT, "out", "shots", "p17_gui_run.png")
VK_F5 = 0x74


def main():
    # 1) 先杀干净，等 3 秒
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3.0)

    # 2) GUI 打开
    h = msui.launch(SRC, wait=8.0)
    print("hwnd =", h, "rect =", G.rect(h))
    msui.shot(h, "p17_gui_open.png")

    # 3) F5 跑仿真
    G.foreground(h)
    time.sleep(0.6)
    G.press(VK_F5)
    print("pressed F5")
    time.sleep(1.0)
    n = msui.dismiss_all()
    print("dialogs:", n)

    # 4) 等 8 秒让仿真跑完
    time.sleep(8.0)
    msui.shot(h, "p17_gui_after8s.png")

    # 再按一次 F5 看看是不是需要 resume
    G.foreground(h)
    G.press(VK_F5)
    time.sleep(3.0)

    # 5) 最终截图
    G.foreground(h)
    time.sleep(0.5)
    G.screenshot(h, SHOT)
    print("shot ->", SHOT)

    # 顺便再截一张整屏，防止窗口截图裁掉了探针框
    G.screenshot_screen(os.path.join(ROOT, "out", "shots", "p17_gui_screen.png"))
    print("screen -> out/shots/p17_gui_screen.png")

    json.dump({"probe_value": None,
               "screenshot": "out/shots/p17_gui_run.png",
               "note": "待人工读图"},
              open(os.path.join(ROOT, "out", "p17_gui.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.stdout.flush()
    # 不杀进程，留着方便后续操作
    os._exit(0)


if __name__ == "__main__":
    main()
