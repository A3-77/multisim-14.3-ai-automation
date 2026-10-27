# -*- coding: utf-8 -*-
"""真实 Multisim GUI 截图（v0.9.1）。

这个模块只做一件事：**把已经生成好的 `.ms14` 用 Multisim 14.3.3 的图形界面打开，
调整视图，然后抓窗口**。不画图、不根据 IR/CSV 合成任何像素 ——
所有 PNG 都是 `PrintWindow` 从真实窗口里抓下来的位图。

两种目标
--------
`schematic`
    打开 -> 关掉启动弹窗 -> 最大化 -> 顶到前台 -> 自适应缩放（Ctrl+滚轮）
    -> 直到整张图（含元件/位号/参数/探针）都落在画布内 -> PrintWindow

`simulation`
    同上打开 -> 菜单「仿真(S)」->「Analyses and simulation(A)」-> 列表里选
    「瞬态分析」-> 填 TSTOP/TMAX -> 点「Run」-> 等「图示仪视图」窗口出现
    -> 抓那个窗口（波形是 Multisim 自己算、自己画的）

坐标是怎么来的
--------------
菜单栏是 BCG 自绘的（`GetMenu` 返回 0，Alt 快捷键也不吃），所以只能点。
菜单项位置用**控件矩形**反推，不写死像素：分析列表是真正的 `ListBox`
（`LB_GETTEXT` 能读出条目文字），参数框/按钮按控件 ID 找。

抓图方式
--------
`PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)` + `GetDIBits`，然后自己用 zlib
编 PNG（`pngio`）。不用 `GetCircuitImage` —— 那是 API 渲染，不是窗口截图。
"""
import ctypes
import ctypes.wintypes as w
import os
import struct
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pngio  # noqa: E402

u = ctypes.windll.user32
g32 = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32

MS_EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
MAIN_CLASS = "Multisim14.3"

# 窗口客户区里"画布"的估算内缩（左侧设计工具箱 ~160 px、顶部工具栏 ~95 px）
CANVAS_MARGIN_L = 165
CANVAS_MARGIN_T = 100
CANVAS_MARGIN_R = 20
CANVAS_MARGIN_B = 40


class CaptureError(Exception):
    def __init__(self, code, message, hint=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self):
        d = {"code": self.code, "message": self.message}
        if self.hint:
            d["hint"] = self.hint
        return d


# ---------------------------------------------------------------- 窗口基础
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def rect(hwnd):
    r = RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def enum_windows():
    out = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, lp):
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        n = u.GetWindowTextLengthW(hwnd)
        txt = ctypes.create_unicode_buffer(n + 2)
        u.GetWindowTextW(hwnd, txt, n + 2)
        out.append({"hwnd": hwnd, "cls": cls.value, "title": txt.value,
                    "vis": bool(u.IsWindowVisible(hwnd))})
        return True

    u.EnumWindows(cb, 0)
    return out


def children(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hh, lp):
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hh, cls, 256)
        n = u.GetWindowTextLengthW(hh)
        txt = ctypes.create_unicode_buffer(n + 2)
        u.GetWindowTextW(hh, txt, n + 2)
        out.append({"hwnd": hh, "cls": cls.value, "txt": txt.value,
                    "id": u.GetDlgCtrlID(hh), "rect": rect(hh),
                    "vis": bool(u.IsWindowVisible(hh))})
        return True

    u.EnumChildWindows(hwnd, cb, 0)
    return out


def child_by_id(hwnd, ctrl_id):
    for c in children(hwnd):
        if c["id"] == ctrl_id:
            return c["hwnd"]
    return 0


def main_hwnd(timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for x in enum_windows():
            if x["cls"] == MAIN_CLASS and x["vis"]:
                l, t, r, b = rect(x["hwnd"])
                if r - l > 200:
                    return x["hwnd"]
        time.sleep(0.5)
    return 0


def foreground(hwnd, retries=8):
    for _ in range(retries):
        if u.GetForegroundWindow() == hwnd:
            return True
        cur = k32.GetCurrentThreadId()
        tgt = u.GetWindowThreadProcessId(hwnd, None)
        fg = u.GetForegroundWindow()
        fgt = u.GetWindowThreadProcessId(fg, None) if fg else 0
        u.AttachThreadInput(cur, tgt, True)
        if fgt:
            u.AttachThreadInput(cur, fgt, True)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        u.SetFocus(hwnd)
        time.sleep(0.25)
        u.AttachThreadInput(cur, tgt, False)
        if fgt:
            u.AttachThreadInput(cur, fgt, False)
        if u.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.3)
    return False


# ---------------------------------------------------------------- 输入
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(w.ULONG))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", w.DWORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ctypes.POINTER(w.ULONG))]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 40)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _U)]


def _send(inp):
    u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def key_down(vk):
    i = INPUT()
    i.type = 1
    i.u.ki.wVk = vk
    i.u.ki.wScan = u.MapVirtualKeyW(vk, 0)
    _send(i)


def key_up(vk):
    i = INPUT()
    i.type = 1
    i.u.ki.wVk = vk
    i.u.ki.wScan = u.MapVirtualKeyW(vk, 0)
    i.u.ki.dwFlags = KEYEVENTF_KEYUP
    _send(i)


def press(vk, delay=0.06):
    key_down(vk)
    time.sleep(delay)
    key_up(vk)
    time.sleep(delay)


def hotkey(*vks):
    for v in vks:
        key_down(v)
        time.sleep(0.02)
    time.sleep(0.03)
    for v in reversed(vks):
        key_up(v)
        time.sleep(0.02)
    time.sleep(0.1)


def type_text(text, per_char=0.02):
    for ch in text:
        code = ord(ch)
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            i = INPUT()
            i.type = 1
            i.u.ki.wVk = 0
            i.u.ki.wScan = code
            i.u.ki.dwFlags = flags
            _send(i)
        time.sleep(per_char)
    time.sleep(0.1)


def click(x, y, settle=0.35, hold=0.04):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.08)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(hold)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(settle)


def click_center(rc, settle=0.35):
    click((rc[0] + rc[2]) // 2, (rc[1] + rc[3]) // 2, settle)


def wheel(delta, times=1, gap=0.12):
    for _ in range(times):
        u.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        time.sleep(gap)


# ---------------------------------------------------------------- 抓图
def capture_window(hwnd, path):
    """PrintWindow 抓整窗 -> PNG。返回 (path, 宽, 高)。"""
    l, t, r, b = rect(hwnd)
    ww, hh = r - l, b - t
    if ww <= 0 or hh <= 0:
        raise CaptureError("WINDOW_GONE", "窗口尺寸为 0：%s" % ((l, t, r, b),))

    hdc = u.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, ww, hh)
    old = g32.SelectObject(mdc, bmp)
    ok = u.PrintWindow(hwnd, mdc, 2)      # PW_RENDERFULLCONTENT

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", w.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", w.WORD),
                    ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                    ("biSizeImage", w.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", w.DWORD),
                    ("biClrImportant", w.DWORD)]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = ww
    bi.biHeight = -hh
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(ww * hh * 4)
    g32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)

    g32.SelectObject(mdc, old)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)

    if not ok:
        raise CaptureError("CAPTURE_FAILED", "PrintWindow 返回 0（窗口可能被遮挡/最小化）")

    data = buf.raw
    rgb = bytearray(ww * hh * 3)
    for y in range(hh):
        row = data[y * ww * 4:(y + 1) * ww * 4]
        o = y * ww * 3
        for x in range(ww):
            i = x * 4
            o3 = o + x * 3
            rgb[o3] = row[i + 2]
            rgb[o3 + 1] = row[i + 1]
            rgb[o3 + 2] = row[i]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    pngio.encode(path, ww, hh, rgb)
    return path, ww, hh


def canvas_region(hwnd):
    l, t, r, b = rect(hwnd)
    return (l + CANVAS_MARGIN_L, t + CANVAS_MARGIN_T,
            r - CANVAS_MARGIN_R, b - CANVAS_MARGIN_B)


def content_fits(path, hwnd, margin=0.03):
    """判断画布里的内容是否完整落在可视区域内（留 margin 边距）。

    只统计**深色**像素：网格点/图纸边框是浅灰，会把包围盒撑满整张画布，
    那样任何缩放都判成"装不下"，自适应就失去意义。
    """
    w, h, ch, _ = pngio.decode(path)
    reg = canvas_region(hwnd)
    l, t, r, b = rect(hwnd)
    x0, y0 = max(0, reg[0] - l), max(0, reg[1] - t)
    x1, y1 = min(w, reg[2] - l), min(h, reg[3] - t)
    bb = pngio.dark_bbox(path, region=(x0, y0, x1, y1))
    if bb is None:
        return False, None
    mw = int((x1 - x0) * margin)
    mh = int((y1 - y0) * margin)
    ok = (bb[0] > x0 + mw and bb[1] > y0 + mh and
          bb[2] < x1 - mw and bb[3] < y1 - mh)
    fill = ((bb[2] - bb[0]) * (bb[3] - bb[1])) / float((x1 - x0) * (y1 - y0))
    return ok, {"bbox": bb, "fill": round(fill, 3), "canvas": (x0, y0, x1, y1)}


def zoom_to_fit(hwnd, tmp_path, max_steps=8):
    """先缩到最小，再逐级放大，停在"刚好装得下且最大"的那一级。

    只动 Ctrl+滚轮（Multisim 的缩放手势），不碰任何电路数据。
    """
    l, t, r, b = rect(hwnd)
    cx, cy = (l + r) // 2, (t + b) // 2
    u.SetCursorPos(cx, cy)
    time.sleep(0.2)
    hotkey(0x11)                      # 松开的 ctrl，防止卡住
    key_down(0x11)
    wheel(-120, max_steps)
    key_up(0x11)
    time.sleep(0.8)

    best = None
    for step in range(max_steps + 1):
        capture_window(hwnd, tmp_path)
        ok, info = content_fits(tmp_path, hwnd)
        if ok:
            best = step
        elif best is not None:
            # 上一步刚好装得下，退回去
            key_down(0x11)
            wheel(120, 1)
            key_up(0x11)
            time.sleep(0.6)
            capture_window(hwnd, tmp_path)
            return {"zoom_steps": best, "info": info}
        if step < max_steps:
            key_down(0x11)
            wheel(120, 1)
            key_up(0x11)
            time.sleep(0.6)
    return {"zoom_steps": best if best is not None else max_steps,
            "info": None}


# ---------------------------------------------------------------- 打开电路
def dismiss_dialogs(rounds=8):
    n = 0
    for _ in range(rounds):
        ds = [x for x in enum_windows() if x["vis"] and x["cls"] == "#32770"]
        if not ds:
            break
        for d in ds:
            ok = u.GetDlgItem(d["hwnd"], 1)
            if ok:
                u.SendMessageW(ok, 0x00F5, 0, 0)      # BM_CLICK
            else:
                u.PostMessageW(d["hwnd"], 0x0010, 0, 0)   # WM_CLOSE
            n += 1
            time.sleep(0.4)
    return n


def kill_multisim():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)


def open_in_gui(ms14_path, timeout=60.0):
    """启动真实 GUI 并打开 .ms14，返回主窗口 hwnd。"""
    if not os.path.isfile(ms14_path):
        raise CaptureError("NO_MS14", "找不到 .ms14：%s" % ms14_path)
    if not os.path.isfile(MS_EXE):
        raise CaptureError("NO_MULTISIM", "找不到 multisim.exe：%s" % MS_EXE)
    kill_multisim()
    subprocess.Popen([MS_EXE, os.path.abspath(ms14_path)])
    h = main_hwnd(timeout)
    if not h:
        raise CaptureError("NO_WINDOW", "Multisim 窗口没起来（%.0fs）" % timeout)
    time.sleep(3.0)
    dismiss_dialogs()
    u.ShowWindow(h, 3)                 # SW_MAXIMIZE
    foreground(h)
    time.sleep(1.2)
    dismiss_dialogs()
    foreground(h)
    return h


# ---------------------------------------------------------------- 仿真截图
def _menu_bar_xy(hwnd, which):
    """菜单栏各项的屏幕坐标（相对窗口原点）。BCG 自绘，只能按位置点。"""
    l, t, _r, _b = rect(hwnd)
    x = {"file": 30, "edit": 80, "view": 135, "place": 185,
         "simulate": 235, "transfer": 290, "tools": 340}[which]
    return l + x, t + 38


def _analysis_list(hwnd):
    return child_by_id(hwnd, 10009)


def _lb_items(lb):
    n = u.SendMessageW(lb, 0x018B, 0, 0)          # LB_GETCOUNT
    items = []
    for i in range(n):
        ln = u.SendMessageW(lb, 0x018A, i, 0)     # LB_GETTEXTLEN
        buf = ctypes.create_unicode_buffer(ln + 2)
        u.SendMessageW(lb, 0x0189, i, buf)        # LB_GETTEXT
        items.append(buf.value)
    return items


def _lb_item_rect(lb, index):
    r = RECT()
    u.SendMessageW(lb, 0x0198, index, ctypes.byref(r))    # LB_GETITEMRECT
    l, t, _r, _b = rect(lb)
    return (l + r.left, t + r.top, l + r.right, t + r.bottom)


def open_analysis_dialog(hwnd, timeout=30.0):
    x, y = _menu_bar_xy(hwnd, "simulate")
    click(x, y, settle=0.9)
    # 「Analyses and simulation(A)」在菜单第 4 个可选项
    click(x + 92, y + 88, settle=2.0)
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in enum_windows():
            if w["vis"] and w["title"] == "Analyses and Simulation":
                return w["hwnd"]
        time.sleep(0.5)
    raise CaptureError("NO_ANALYSIS_DIALOG",
                       "没等到 Analyses and Simulation 对话框",
                       "菜单项位置可能随语言/版本变化，检查 docs/v0.9.1-screenshot.md")


def select_transient(dlg):
    lb = _analysis_list(dlg)
    if not lb:
        raise CaptureError("NO_ANALYSIS_LIST", "对话框里找不到分析列表（id=10009）")
    items = _lb_items(lb)
    idx = None
    for i, s in enumerate(items):
        if "瞬态" in s or "Transient" in s:
            idx = i
            break
    if idx is None:
        raise CaptureError("NO_TRANSIENT_ITEM",
                           "分析列表里没有瞬态分析：%s" % items)
    click_center(_lb_item_rect(lb, idx), settle=1.2)
    return idx, items


def _panel(dlg):
    """当前显示的参数面板（嵌套 #32770）。瞬态面板的控件 id 是 104。"""
    for c in children(dlg):
        if c["cls"] == "#32770" and c["id"] == 104:
            return c["hwnd"]
    for c in children(dlg):
        if c["cls"] == "#32770" and "分析参数" in c["txt"]:
            return c["hwnd"]
    return 0


def set_param(panel, ctrl_id, value):
    """把数值写进参数框：先点进去，再 Ctrl+A 覆盖输入。"""
    h = child_by_id(panel, ctrl_id)
    if not h:
        return False
    click_center(rect(h), settle=0.3)
    hotkey(0x11, 0x41)          # Ctrl+A
    type_text(value)
    time.sleep(0.2)
    return True


def run_gui_transient(dlg, tstop="0.01", tmax="1e-5"):
    panel = _panel(dlg)
    if not panel:
        raise CaptureError("NO_PARAM_PANEL", "找不到瞬态参数面板")
    ok_stop = set_param(panel, 10034, tstop)
    ok_max = set_param(panel, 10040, tmax)
    run_btn = child_by_id(dlg, 10265)
    if not run_btn:
        raise CaptureError("NO_RUN_BUTTON", "对话框里找不到 Run 按钮（id=10265）")
    click_center(rect(run_btn), settle=1.5)
    return {"tstop_set": ok_stop, "tmax_set": ok_max}


def wait_window(title_contains, timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for x in enum_windows():
            if x["vis"] and title_contains.lower() in x["title"].lower():
                l, t, r, b = rect(x["hwnd"])
                if r - l > 200 and b - t > 150:
                    return x["hwnd"]
        time.sleep(0.5)
    return 0


# ---------------------------------------------------------------- 对外 API
def capture_schematic(ms14_path, out_path, log=print):
    h = open_in_gui(ms14_path)
    log("  Multisim 主窗口 hwnd=%d rect=%s" % (h, rect(h)))
    tmp = os.path.join(os.path.dirname(os.path.abspath(out_path)), "_zoom_probe.png")
    z = zoom_to_fit(h, tmp)
    log("  自适应缩放：%s" % z)
    foreground(h)
    time.sleep(0.6)
    p, ww, hh = capture_window(h, out_path)
    if os.path.isfile(tmp):
        os.remove(tmp)
    ok, info = content_fits(p, h)
    return {"path": p, "width": ww, "height": hh, "zoom": z,
            "content_ok": ok, "content": info,
            "method": "PrintWindow(PW_RENDERFULLCONTENT) + GetDIBits -> zlib PNG",
            "window_title": "Multisim 14.3", "hwnd": h}


def capture_simulation(ms14_path, out_path, tstop="0.01", tmax="1e-5", log=print):
    h = open_in_gui(ms14_path)
    log("  Multisim 主窗口 hwnd=%d" % h)
    dlg = open_analysis_dialog(h)
    log("  Analyses and Simulation hwnd=%d rect=%s" % (dlg, rect(dlg)))
    idx, items = select_transient(dlg)
    log("  选中第 %d 项（列表共 %d 项）" % (idx, len(items)))
    params = run_gui_transient(dlg, tstop, tmax)
    log("  参数写入：%s，已点 Run" % params)
    gw = wait_window("图示仪", timeout=90.0) or wait_window("Grapher", timeout=5.0)
    if not gw:
        raise CaptureError("NO_GRAPHER", "Run 之后没有出现图示仪（Grapher）窗口",
                           "确认电路有探针、分析项选的是瞬态分析")
    time.sleep(1.5)
    u.ShowWindow(gw, 3)
    foreground(gw)
    time.sleep(1.0)
    p, ww, hh = capture_window(gw, out_path)
    return {"path": p, "width": ww, "height": hh, "hwnd": gw,
            "dialog_items": items, "selected_index": idx, "params": params,
            "method": "PrintWindow(PW_RENDERFULLCONTENT) + GetDIBits -> zlib PNG",
            "window_title": "图示仪视图 / Grapher View"}


def capture(ms14_path, out_path, target="schematic", tstop="0.01", tmax="1e-5",
            log=print):
    if target == "schematic":
        return capture_schematic(ms14_path, out_path, log=log)
    if target in ("simulation", "waveform", "grapher"):
        return capture_simulation(ms14_path, out_path, tstop, tmax, log=log)
    raise CaptureError("BAD_TARGET", "target 只能是 schematic 或 simulation",
                       "拿到 %r" % (target,))


if __name__ == "__main__":
    import json
    a = sys.argv[1:]
    if len(a) < 2:
        print("用法: screenshot.py <ms14> <out.png> [schematic|simulation]")
        sys.exit(2)
    print(json.dumps(capture(a[0], a[1], a[2] if len(a) > 2 else "schematic"),
                     ensure_ascii=False, indent=2))
