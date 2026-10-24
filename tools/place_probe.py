# -*- coding: utf-8 -*-
"""用 Multisim 自己的 UI 放一个电压探针，然后保存 —— 借它生成探针模板。

Multisim 由 Popen 启动时，启动它的进程退出后子进程也会被收走，
所以整个流程必须放在同一次执行里完成。

用法：
    python tools/place_probe.py out/probe_src.ms14 [探针按钮x y] [导线x y]
"""
import ctypes
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
OUT = os.path.join(ROOT, "out")
SHOTS = os.path.join(OUT, "shots")
os.makedirs(SHOTS, exist_ok=True)
u = ctypes.windll.user32


def dismiss_all():
    n = 0
    for _ in range(15):
        ds = G.visible_dialogs()
        if not ds:
            break
        for d in ds:
            hwnd = d["hwnd"]
            ok = u.GetDlgItem(hwnd, 1)
            if ok:
                u.SendMessageW(ok, 0x00F5, 0, 0)
            else:
                G.foreground(hwnd)
                G.press(0x0D)
            n += 1
            time.sleep(0.35)
    return n


def find_main():
    for _ in range(40):
        cand = [w for w in G.enum_windows()
                if "multisim" in w["title"].lower() and "[" in w["title"]]
        if cand:
            return cand[0]["hwnd"]
        time.sleep(0.5)
    return None


def shot(hwnd, name):
    p = os.path.join(SHOTS, name)
    try:
        G.screenshot(hwnd, p)
        return p
    except Exception as e:
        return "FAIL %s" % e


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "probe_src.ms14")
    if not os.path.isabs(src):
        src = os.path.join(ROOT, src)
    btn = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 4 else (899, 106)
    wire = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (523, 349)

    subprocess.Popen([EXE, src])
    time.sleep(6)
    n = dismiss_all()
    hwnd = find_main()
    print("dismissed", n, "hwnd", hwnd, flush=True)
    if not hwnd:
        return
    G.foreground(hwnd)
    time.sleep(0.8)
    print("before:", shot(hwnd, "p1_before.png"), flush=True)

    # 1) 点“电压探针”按钮
    G.click(*btn)
    time.sleep(0.8)
    print("btn:", shot(hwnd, "p2_btn.png"), flush=True)

    # 2) 点导线
    G.click(*wire)
    time.sleep(1.0)
    print("wire:", shot(hwnd, "p3_wire.png"), flush=True)

    # 3) 保存
    G.foreground(hwnd)
    G.hotkey("ctrl", "s")
    time.sleep(1.5)
    d = dismiss_all()
    print("saved, extra dialogs", d, flush=True)
    print("after:", shot(hwnd, "p4_saved.png"), flush=True)
    print("DONE")


main()
