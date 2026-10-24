# -*- coding: utf-8 -*-
"""尝试触发 Multisim 的"放置元件"命令：
   A. 给主窗口发 Ctrl+W
   B. 给各个 *Command 窗口 PostMessage(WM_COMMAND, 1376324)
看"选择一个元器件"对话框会不会弹出来。"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

u32 = ctypes.windll.user32
EP = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

CMD_PLACE = 1376324


def windows():
    out = []

    def cb(h, l):
        cls = ctypes.create_unicode_buffer(128)
        t = ctypes.create_unicode_buffer(300)
        u32.GetClassNameW(h, cls, 128)
        u32.GetWindowTextW(h, t, 300)
        out.append((h, cls.value, t.value, bool(u32.IsWindowVisible(h))))
        return True

    u32.EnumWindows(EP(cb), 0)
    return out


def find(pred):
    return [w for w in windows() if pred(w)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 24)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def key(vk, up=False):
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(vk, 0, 2 if up else 0, 0, None)
    u32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
    time.sleep(0.04)


def combo_ctrl_w():
    key(0x11); key(0x57); key(0x57, True); key(0x11, True)


def dialog_state():
    return [(w[2], w[3]) for w in find(lambda w: w[1] == "#32770" and "元器件" in w[2])]


with Multisim() as ms:
    c = ms.new()
    time.sleep(1.0)
    print("电路:", c.name)
    print("对话框初始状态:", dialog_state())

    frame = find(lambda w: w[1] == "LVFrame" and w[3])
    print("主窗口:", frame[:1])

    # ---- A: 键盘 ----
    if frame:
        h = frame[0][0]
        u32.ShowWindow(h, 9)
        u32.SwitchToThisWindow(h, True)
        time.sleep(0.4)
        print("A) 焦点就绪:", u32.GetForegroundWindow() == h)
        combo_ctrl_w()
        time.sleep(1.5)
        print("A) Ctrl+W 后:", dialog_state())

    # ---- B: WM_COMMAND ----
    targets = find(lambda w: "Command" in w[1] or w[1].startswith("Afx:"))
    print("\nB) 候选命令窗口 %d 个:" % len(targets))
    for h, cls, title, vis in targets:
        print("   %-28s %s" % (title or cls, cls))
    for h, cls, title, vis in targets:
        u32.PostMessageW(h, 0x0111, CMD_PLACE, 0)
        time.sleep(0.35)
        st = dialog_state()
        if any(v for _, v in st):
            print("   !! %r 触发了对话框: %s" % (title, st))
            break
    else:
        print("   B) 没有反应")
    time.sleep(1)
    print("\n最终对话框状态:", dialog_state())
