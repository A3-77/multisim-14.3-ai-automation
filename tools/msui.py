# -*- coding: utf-8 -*-
"""Multisim UI 操作小工具：启动、等窗口、点掉弹窗、截图。

用法（同一个进程里跑完整个流程）：
    import msui
    h = msui.launch(r"out\probe_src.ms14")
    msui.click_img(h, 899, 106)     # 传截图里的像素坐标，自动换算成屏幕坐标
"""
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
SHOTS = os.path.join(ROOT, "out", "shots")
os.makedirs(SHOTS, exist_ok=True)
u = ctypes.windll.user32


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   capture_output=True)


def dismiss_all(rounds=20):
    n = 0
    for _ in range(rounds):
        ds = G.visible_dialogs()
        if not ds:
            break
        for d in ds:
            ok = u.GetDlgItem(d["hwnd"], 1)
            if ok:
                u.SendMessageW(ok, 0x00F5, 0, 0)
            else:
                G.foreground(d["hwnd"])
                G.press(0x0D)
            n += 1
            time.sleep(0.35)
    return n


def find_main(timeout=40.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        cand = [w for w in G.enum_windows()
                if "multisim" in w["title"].lower() and "[" in w["title"]]
        if cand:
            return cand[0]["hwnd"]
        time.sleep(0.5)
    return None


def launch(path, wait=5.0):
    if not os.path.isabs(path):
        path = os.path.join(ROOT, path)
    subprocess.Popen([EXE, path])
    time.sleep(wait)
    dismiss_all()
    h = find_main()
    if not h:
        raise RuntimeError("Multisim 窗口没起来")
    G.foreground(h)
    time.sleep(0.8)
    return h


def shot(h, name):
    p = os.path.join(SHOTS, name)
    G.screenshot(h, p)
    return p


def to_screen(h, x, y):
    l, t, _, _ = G.rect(h)
    return l + int(x), t + int(y)


def click_img(h, x, y, settle=0.7):
    sx, sy = to_screen(h, x, y)
    G.foreground(h)
    time.sleep(0.2)
    G.click(sx, sy)
    time.sleep(settle)
    return sx, sy
