# -*- coding: utf-8 -*-
"""调试：为什么 GetCircuitImage 少画了 V1 / C1。

对比三种取图方式：
  1. open 后立刻 snapshot
  2. 等 4 秒再 snapshot
  3. 整窗口 GUI 截图（看 Multisim 实际显示什么）
"""
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
    print("opened, probes=%s comps=%s" % (circ.probes(), circ.components()))

    p1 = os.path.join(DIR, "shot_immediate.png")
    circ.snapshot(p1)
    print("1) immediate -> %d bytes" % os.path.getsize(p1))

    time.sleep(4.0)
    p2 = os.path.join(DIR, "shot_delayed.png")
    circ.snapshot(p2)
    print("2) +4s       -> %d bytes" % os.path.getsize(p2))

    hwnds = guiauto.find(title_contains="Multisim", visible_only=True)
    print("3) windows = %r" % (hwnds,))
    if hwnds:
        hwnd = hwnds[0]["hwnd"]
        guiauto.foreground(hwnd)
        time.sleep(1.0)
        p3 = os.path.join(DIR, "shot_window.png")
        guiauto.screenshot(hwnd, p3)
        print("   window -> %d bytes  rect=%s"
              % (os.path.getsize(p3), guiauto.rect(hwnd)))

    try:
        circ.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
