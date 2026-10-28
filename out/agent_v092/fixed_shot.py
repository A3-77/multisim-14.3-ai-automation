# -*- coding: utf-8 -*-
"""固定配方重拍三张原理图：打开 -> 点画布 -> Ctrl+滚轮缩小 3 格 -> 抓窗口。

不用自适应缩放（zoom_to_fit 闭环在 v0.9.2 未收敛，见 docs/agent-acceptance-v0.9.2.md）。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import screenshot as SS  # noqa: E402

NOTCHES = int(sys.argv[1]) if len(sys.argv) > 1 else 3

for case in ("case_a_rc", "case_b_rectifier", "case_c_iterative"):
    d = os.path.join(ROOT, "out", "agent_v092", case)
    h = SS.open_in_gui(os.path.join(d, "circuit.ms14"))
    SS.foreground(h)
    time.sleep(0.8)
    l, t, r, b = SS.rect(h)
    SS.click((l + r) // 2, (t + b) // 2)
    time.sleep(0.4)
    SS.key_down(0x11)
    SS.wheel(-120, NOTCHES)
    SS.key_up(0x11)
    time.sleep(1.0)
    p = os.path.join(d, "01_schematic.png")
    _, ww, hh = SS.capture_window(h, p)
    ok, info = SS.content_fits(p, h, pad_px=4, whole_sheet=False)
    print("%-18s %dx%d content_ok=%s fill=%s bbox=%s" % (
        case, ww, hh, ok, info and info["fill"], info and info["bbox"]))
