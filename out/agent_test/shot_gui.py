# -*- coding: utf-8 -*-
"""把 Multisim 窗口显示出来再截图（GUI 截图），对比 GetCircuitImage 的差异。"""
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

    hwnds = guiauto.find(title_contains="Multisim", visible_only=False)
    print("windows=%r" % (hwnds,))
    hwnd = hwnds[0]["hwnd"]
    guiauto.show(hwnd, 3)          # 3 = maximize
    time.sleep(2.0)
    guiauto.foreground(hwnd)
    time.sleep(2.0)
    print("rect=%s" % (guiauto.rect(hwnd),))

    p = os.path.join(DIR, "shot_gui.png")
    guiauto.screenshot(hwnd, p)
    print("gui -> %d bytes" % os.path.getsize(p))

    # 同时再导一次 API 图，便于对比
    p2 = os.path.join(DIR, "shot_api.png")
    circ.snapshot(p2)
    print("api -> %d bytes" % os.path.getsize(p2))

    try:
        circ.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
