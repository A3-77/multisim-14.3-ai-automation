# -*- coding: utf-8 -*-
"""最小的 Win32 GUI 驱动层：找窗口 / 顶前台 / 按键 / 点击 / 截图。

只依赖 ctypes + stdlib，能跑在 runtime/py32 里。
"""
import ctypes
import ctypes.wintypes as w
import os
import struct
import time
import zlib

u = ctypes.windll.user32
g32 = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32

# ---------------------------------------------------------------- 窗口
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


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
        out.append({"hwnd": hwnd, "cls": cls.value, "title": txt.value,
                    "pid": pid.value, "vis": bool(u.IsWindowVisible(hwnd))})
        return True

    u.EnumWindows(cb, 0)
    return out


def rect(hwnd):
    r = RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def find(cls=None, title_contains=None, pid=None, visible_only=False):
    res = []
    for x in enum_windows():
        if cls and x["cls"] != cls:
            continue
        if title_contains and title_contains.lower() not in x["title"].lower():
            continue
        if pid is not None and x["pid"] != pid:
            continue
        if visible_only and not x["vis"]:
            continue
        res.append(x)
    return res


def multisim_pids():
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq multisim.exe", "/FO", "CSV"],
                         capture_output=True, text=True, encoding="gbk", errors="ignore").stdout
    pids = set()
    for line in out.splitlines()[1:]:
        parts = line.strip().strip('"').split('","')
        if len(parts) > 1 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def show(hwnd, cmd=1):
    u.ShowWindow(hwnd, cmd)
    time.sleep(0.2)


def foreground(hwnd, retries=6):
    """把窗口顶到前台并确认成功。返回 (ok, 实际前台 hwnd)。"""
    for _ in range(retries):
        fg = u.GetForegroundWindow()
        if fg == hwnd:
            return True, fg
        cur = k32.GetCurrentThreadId()
        tgt = u.GetWindowThreadProcessId(hwnd, None)
        fgt = u.GetWindowThreadProcessId(fg, None) if fg else 0
        u.AttachThreadInput(cur, tgt, True)
        if fgt:
            u.AttachThreadInput(cur, fgt, True)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        u.SetFocus(hwnd)
        time.sleep(0.2)
        u.AttachThreadInput(cur, tgt, False)
        if fgt:
            u.AttachThreadInput(cur, fgt, False)
        if u.GetForegroundWindow() == hwnd:
            return True, hwnd
        time.sleep(0.25)
    return False, u.GetForegroundWindow()


# ---------------------------------------------------------------- 输入
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(w.ULONG))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(w.ULONG))]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 40)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _U)]


def _send(inp):
    u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def key_down(vk):
    i = INPUT(); i.type = INPUT_KEYBOARD
    i.u.ki.wVk = vk; i.u.ki.wScan = u.MapVirtualKeyW(vk, 0); i.u.ki.dwFlags = 0
    _send(i)


def key_up(vk):
    i = INPUT(); i.type = INPUT_KEYBOARD
    i.u.ki.wVk = vk; i.u.ki.wScan = u.MapVirtualKeyW(vk, 0); i.u.ki.dwFlags = KEYEVENTF_KEYUP
    _send(i)


def press(vk, delay=0.05):
    key_down(vk); time.sleep(delay); key_up(vk); time.sleep(delay)


VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "esc": 0x1B, "enter": 0x0D,
      "tab": 0x09, "space": 0x20, "del": 0x2E, "back": 0x08, "up": 0x26,
      "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
      "pgup": 0x21, "pgdn": 0x22, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
      "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79}


def hotkey(*keys):
    """hotkey('ctrl','w') / hotkey('ctrl','shift','s') / hotkey('esc')"""
    codes = []
    for k in keys:
        codes.append(VK.get(k.lower(), ord(k.upper()) if len(k) == 1 else None))
    codes = [c for c in codes if c is not None]
    for c in codes:
        key_down(c); time.sleep(0.02)
    time.sleep(0.03)
    for c in reversed(codes):
        key_up(c); time.sleep(0.02)
    time.sleep(0.08)


def type_text(text, per_char=0.012):
    """逐字符 Unicode 输入（不受输入法/键盘布局影响）。"""
    for ch in text:
        code = ord(ch)
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            i = INPUT(); i.type = INPUT_KEYBOARD
            i.u.ki.wVk = 0
            i.u.ki.wScan = code
            i.u.ki.dwFlags = flags
            _send(i)
        time.sleep(per_char)
    time.sleep(0.1)


def click(x, y, button="left", double=False, settle=0.25):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    dn = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
    up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
    u.mouse_event(dn, 0, 0, 0, 0)
    time.sleep(0.03)
    u.mouse_event(up, 0, 0, 0, 0)
    if double:
        time.sleep(0.06)
        u.mouse_event(dn, 0, 0, 0, 0)
        time.sleep(0.03)
        u.mouse_event(up, 0, 0, 0, 0)
    time.sleep(settle)


def drag(x1, y1, x2, y2, steps=18, settle=0.3):
    u.SetCursorPos(int(x1), int(y1))
    time.sleep(0.05)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    for i in range(1, steps + 1):
        u.SetCursorPos(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.012)
    time.sleep(0.05)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(settle)


# ---------------------------------------------------------------- 截图
def screenshot(hwnd, path):
    """用 PrintWindow 抓窗口内容，写成 PNG（纯 stdlib 编码）。"""
    l, t, r, b = rect(hwnd)
    ww, hh = r - l, b - t
    if ww <= 0 or hh <= 0:
        raise RuntimeError("窗口尺寸为 0: %s" % ((l, t, r, b),))

    hdc = u.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, ww, hh)
    g32.SelectObject(mdc, bmp)

    ok = u.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", w.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                    ("biSizeImage", w.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = ww
    bi.biHeight = -hh
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(ww * hh * 4)
    g32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)

    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)

    raw = bytearray()
    data = buf.raw
    for y in range(hh):
        row = data[y * ww * 4:(y + 1) * ww * 4]
        raw.append(0)
        for x in range(ww):
            b_, g_, r_, _a = row[x * 4:x * 4 + 4]
            raw += bytes((r_, g_, b_))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", ww, hh, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return path, ok, (ww, hh)


# ---------------------------------------------------------------- 剪贴板
def screenshot_screen(path):
    """抓整个屏幕（虚拟桌面），用来看到任何弹窗。"""
    x = u.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
    y = u.GetSystemMetrics(77)
    ww = u.GetSystemMetrics(78)
    hh = u.GetSystemMetrics(79)
    if ww <= 0:
        ww, hh, x, y = u.GetSystemMetrics(0), u.GetSystemMetrics(1), 0, 0
    hdc = u.GetDC(0)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, ww, hh)
    g32.SelectObject(mdc, bmp)
    g32.BitBlt(mdc, 0, 0, ww, hh, hdc, x, y, 0x00CC0020)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", w.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                    ("biSizeImage", w.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = ww
    bi.biHeight = -hh
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(ww * hh * 4)
    g32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u.ReleaseDC(0, hdc)

    raw = bytearray()
    data = buf.raw
    for yy in range(hh):
        row = data[yy * ww * 4:(yy + 1) * ww * 4]
        raw.append(0)
        for xx in range(ww):
            b_, g_, r_, _a = row[xx * 4:xx * 4 + 4]
            raw += bytes((r_, g_, b_))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", ww, hh, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return path, (ww, hh)


def dlg_message(hwnd):
    """读取 Multisim 消息框里的正文（正文放在 id=52 的 Edit 里）。"""
    ed = u.GetDlgItem(hwnd, 52)
    if not ed:
        return ""
    buf = ctypes.create_unicode_buffer(8192)
    u.SendMessageW(ed, 0x000D, 8192, buf)
    return buf.value


def visible_dialogs():
    return [x for x in enum_windows() if x["cls"] == "#32770" and x["vis"]]


def clipboard_formats(dump_dir=None, tag="clip"):
    got = []
    if not u.OpenClipboard(None):
        return got
    try:
        fmt = 0
        while True:
            fmt = u.EnumClipboardFormats(fmt)
            if fmt == 0:
                break
            name = ctypes.create_unicode_buffer(256)
            n = u.GetClipboardFormatNameW(fmt, name, 256)
            label = name.value if n else "std%d" % fmt
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
    finally:
        u.CloseClipboard()
    if dump_dir:
        os.makedirs(dump_dir, exist_ok=True)
        for fmt, label, size, data in got:
            if not data:
                continue
            safe = "".join(c if c.isalnum() else "_" for c in label)[:36]
            with open(os.path.join(dump_dir, "%s_%d_%s.bin" % (tag, fmt, safe)), "wb") as f:
                f.write(data)
    return got
