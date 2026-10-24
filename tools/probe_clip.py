# -*- coding: utf-8 -*-
"""探查 Multisim 的剪贴板格式。

思路：如果能往剪贴板里放 Multisim 认识的电路数据，再 Ctrl+V，
就等于绕过了 .ms14 压缩格式，直接"创建"电路。

步骤：
  1. COM 打开一个样例电路（这样画布上有东西可选）
  2. 把 Multisim 主窗口顶到前台
  3. 发 Ctrl+A / Ctrl+C
  4. 枚举剪贴板所有格式，把原始字节 dump 出来
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

u = ctypes.windll.user32
k32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13


def enum_windows():
    out = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, lp):
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        txt = ctypes.create_unicode_buffer(512)
        u.GetWindowTextW(hwnd, txt, 512)
        pid = w.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((hwnd, cls.value, txt.value, pid.value, bool(u.IsWindowVisible(hwnd))))
        return True

    u.EnumWindows(cb, 0)
    return out


def multisim_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq multisim.exe", "/FO", "CSV"],
                         capture_output=True, text=True, encoding="gbk", errors="ignore").stdout
    pids = set()
    for line in out.splitlines()[1:]:
        parts = line.strip().strip('"').split('","')
        if len(parts) > 1 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def force_foreground(hwnd):
    fg = u.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_tid = k32.GetCurrentThreadId()
    tgt_tid = u.GetWindowThreadProcessId(hwnd, None)
    fg_tid = u.GetWindowThreadProcessId(fg, None) if fg else 0
    u.AttachThreadInput(cur_tid, tgt_tid, True)
    if fg_tid:
        u.AttachThreadInput(cur_tid, fg_tid, True)
    u.ShowWindow(hwnd, 9)
    u.BringWindowToTop(hwnd)
    ok = bool(u.SetForegroundWindow(hwnd))
    u.SetFocus(hwnd)
    time.sleep(0.3)
    u.AttachThreadInput(cur_tid, tgt_tid, False)
    if fg_tid:
        u.AttachThreadInput(cur_tid, fg_tid, False)
    return u.GetForegroundWindow() == hwnd or ok


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(w.ULONG))]


class _I(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _I)]


def send_key(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = u.MapVirtualKeyW(vk, 0)
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def ctrl_key(vk):
    send_key(VK_CONTROL)
    time.sleep(0.03)
    send_key(vk)
    time.sleep(0.03)
    send_key(vk, True)
    time.sleep(0.03)
    send_key(VK_CONTROL, True)
    time.sleep(0.15)


def dump_clipboard(tag):
    if not u.OpenClipboard(None):
        print("OpenClipboard 失败 err=%d" % ctypes.GetLastError())
        return []
    got = []
    try:
        fmt = 0
        while True:
            fmt = u.EnumClipboardFormats(fmt)
            if fmt == 0:
                break
            name = ctypes.create_unicode_buffer(256)
            n = u.GetClipboardFormatNameW(fmt, name, 256)
            label = name.value if n else "(std %d)" % fmt
            h = u.GetClipboardData(fmt)
            size, data = 0, b""
            if h:
                size = k32.GlobalSize(h)
                p = k32.GlobalLock(h)
                if p:
                    try:
                        data = ctypes.string_at(p, min(size, 400000)) if size else b""
                    finally:
                        k32.GlobalUnlock(h)
            got.append((fmt, label, size, data))
            print("  fmt=%-6d %-42s size=%-8d head=%r" % (fmt, label, size, data[:70]))
    finally:
        u.CloseClipboard()

    d = os.path.join(ROOT, "out", "clip")
    os.makedirs(d, exist_ok=True)
    for fmt, label, size, data in got:
        if not data:
            continue
        safe = "".join(c if c.isalnum() else "_" for c in label)[:40]
        with open(os.path.join(d, "%s_%d_%s.bin" % (tag, fmt, safe)), "wb") as f:
            f.write(data)
    return got


def main():
    import msc

    sample = os.path.join(ROOT, "samples", "7812.ms12")
    print("[1] COM 打开", os.path.basename(sample))
    ms = msc.Multisim()
    print("    版本:", ms.version)
    cir = ms.open(sample)
    print("    电路:", cir.name, "元件数:", len(cir.components()))

    pids = multisim_pids()
    print("[2] multisim pid:", pids)
    ws = [x for x in enum_windows() if x[3] in pids]
    print("    属于该进程的顶层窗口 %d 个:" % len(ws))
    for x in ws:
        print("      hwnd=%-8d vis=%-5s class=%-24s title=%r" % (x[0], x[4], x[1], x[2][:60]))

    if not ws:
        print("[!] 没有顶层窗口")
        return
    main_win = next((x for x in ws if x[4] and x[2]), ws[0])
    print("[3] 目标窗口:", main_win[0], main_win[1], repr(main_win[2][:40]))
    print("    强制前台:", force_foreground(main_win[0]))
    time.sleep(0.6)
    fg = u.GetForegroundWindow()
    print("    当前前台:", fg, "匹配:", fg == main_win[0])
    if fg != main_win[0]:
        print("[!] 拿不到前台，放弃（避免按键打到别的窗口）")
        return

    print("[4] 发 Ctrl+A / Ctrl+C")
    ctrl_key(ord("A"))
    time.sleep(0.4)
    ctrl_key(ord("C"))
    time.sleep(1.5)

    print("[5] 剪贴板:")
    dump_clipboard("sel")


if __name__ == "__main__":
    main()
