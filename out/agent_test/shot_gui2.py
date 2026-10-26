# -*- coding: utf-8 -*-
"""显示真正的电路窗口（cls=Multisim14.3）再截图。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import msc       # noqa: E402
import guiauto   # noqa: E402

MS14 = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                    "agent_rc_500hz.ms14")
DIR = os.path.join(ROOT, "out", "agent_test")


def main():
    ms = msc.Multisim()
    circ = ms.open(MS14)
    print("opened comps=%s" % (circ.components(),))
    time.sleep(1.0)

    # 真正的电路窗口是 cls='Multisim14.3'，默认隐藏
    wins = guiauto.find(cls="Multisim14.3")
    print("circuit windows=%r" % (wins,))
    if not wins:
        print("没找到 cls=Multisim14.3")
        return
    hwnd = wins[0]["hwnd"]
    guiauto.show(hwnd, 3)          # maximize
    time.sleep(2.5)
    guiauto.foreground(hwnd)
    time.sleep(2.0)
    print("rect=%s" % (guiauto.rect(hwnd),))

    p = os.path.join(DIR, "shot_gui2.png")
    guiauto.screenshot(hwnd, p)
    print("gui -> %d bytes" % os.path.getsize(p))

    ps = os.path.join(DIR, "shot_screen.png")
    guiauto.screenshot_screen(ps)
    print("screen -> %d bytes" % os.path.getsize(ps))

    try:
        circ.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
