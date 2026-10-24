# -*- coding: utf-8 -*-
"""GUI 输入可达性测试：给 Multisim 发 Ctrl+N，看标题栏里的设计编号会不会变。"""
import ctypes, ctypes.wintypes as wt, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

u32 = ctypes.windll.user32

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 24)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]

VK_CONTROL, VK_N, KEYEVENTF_KEYUP = 0x11, 0x4E, 0x0002


def send_combo(vk, ctrl=True):
    seq = []
    if ctrl:
        seq.append((VK_CONTROL, 0))
    seq.append((vk, 0))
    seq.append((vk, KEYEVENTF_KEYUP))
    if ctrl:
        seq.append((VK_CONTROL, KEYEVENTF_KEYUP))
    for code, flags in seq:
        inp = INPUT(type=1)
        inp.ki = KEYBDINPUT(code, 0, flags, 0, None)
        u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.03)


EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def find_frame():
    res = []

    def cb(hwnd, lparam):
        cls = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(hwnd, cls, 128)
        if cls.value == "LVFrame" and u32.IsWindowVisible(hwnd):
            t = ctypes.create_unicode_buffer(300)
            u32.GetWindowTextW(hwnd, t, 300)
            res.append((hwnd, t.value))
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return res


with Multisim() as ms:
    c = ms.new()
    print("COM 侧电路名:", c.name)
    time.sleep(0.5)
    frames = find_frame()
    print("窗口:", frames)
    if not frames:
        sys.exit(1)
    hwnd, title = frames[0]
    print("标题(发送前):", title)

    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    print("前台窗口:", u32.GetForegroundWindow() == hwnd)

    send_combo(VK_N)
    time.sleep(1.5)

    frames = find_frame()
    print("标题(发送后):", frames[0][1] if frames else "窗口没了")
