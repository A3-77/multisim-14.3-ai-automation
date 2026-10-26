# -*- coding: utf-8 -*-
"""P17 续：点工具栏"运行"按钮真正启动仿真，再截图读探针。

F5 没生效（状态栏仍 Interactive、探针框 V(rms) 为 ---）。
这里改成点工具栏绿色三角，并且轮询窗口标题/状态，等仿真真的跑起来。

用法：runtime\\py32\\python.exe tools\\p17_run2.py
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G  # noqa: E402
import msui  # noqa: E402

SHOT = os.path.join(ROOT, "out", "shots", "p17_gui_run.png")


def find_hwnd():
    cand = [w for w in G.enum_windows()
            if "multisim" in w["title"].lower() and "[" in w["title"]]
    return cand[0]["hwnd"] if cand else None


def main():
    h = find_hwnd()
    if h is None:
        print("Multisim 没开着，重新启动")
        msui.kill()
        time.sleep(3.0)
        h = msui.launch(os.path.join(ROOT, "out", "p15_div3.ms14"), wait=8.0)
    print("hwnd =", h, "title =", [w for w in G.enum_windows() if w["hwnd"] == h][0]["title"])

    G.foreground(h)
    time.sleep(0.8)

    # 工具栏绿色三角（窗口坐标，实测自截图 418,86）
    for (x, y, label) in ((418, 86, "play"), (431, 86, "play2")):
        print("click %s @ (%d,%d)" % (label, x, y))
        msui.click_img(h, x, y, settle=1.0)
        time.sleep(1.0)
        msui.shot(h, "p17_click_%s.png" % label)

    print("dialogs:", msui.dismiss_all())
    time.sleep(6.0)

    G.foreground(h)
    time.sleep(0.5)
    G.screenshot(h, SHOT)
    G.screenshot_screen(os.path.join(ROOT, "out", "shots", "p17_gui_screen.png"))
    print("shot ->", SHOT)

    # 也试一次 F5 / Ctrl+R 作为兜底
    for vk, name in ((0x74, "F5"), (0x52, "R")):
        G.foreground(h)
        G.press(vk, delay=0.1)
        time.sleep(2.0)
        print("pressed", name)
    G.screenshot(h, os.path.join(ROOT, "out", "shots", "p17_after_keys.png"))

    json.dump({"probe_value": None,
               "screenshot": "out/shots/p17_gui_run.png",
               "note": "见 p17_click_play.png / p17_gui_run.png"},
              open(os.path.join(ROOT, "out", "p17_gui.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
