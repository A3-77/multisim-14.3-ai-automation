# -*- coding: utf-8 -*-
"""跨进程读 MFC 工具栏按钮信息。

TB_GETBUTTON / TB_GETITEMRECT 要把结果写到调用进程给的指针上，
跨进程时必须先在目标进程里分配内存，再读回来。
"""
import ctypes
import ctypes.wintypes as wt

u = ctypes.windll.user32
k32 = ctypes.windll.kernel32

k32.OpenProcess.restype = ctypes.c_void_p
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                               wt.DWORD, wt.DWORD]
k32.VirtualFreeEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.CloseHandle.argtypes = [ctypes.c_void_p]

u.SendMessageW.restype = ctypes.c_ssize_t
u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]

PROCESS_VM = 0x0008 | 0x0010 | 0x0020 | 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_RW = 0x04
MEM_RELEASE = 0x8000

TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
TB_GETITEMRECT = 0x041D
TB_GETBUTTONTEXTW = 0x044B


class TBBUTTON(ctypes.Structure):
    _fields_ = [
        ("iBitmap", ctypes.c_int),
        ("idCommand", ctypes.c_int),
        ("fsState", ctypes.c_ubyte),
        ("fsStyle", ctypes.c_ubyte),
        ("bReserved", ctypes.c_ubyte * 6),
        ("dwData", ctypes.c_size_t),
        ("iString", ctypes.c_ssize_t),
    ]


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class Remote:
    def __init__(self, hwnd):
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        self.pid = pid.value
        self.hp = k32.OpenProcess(PROCESS_VM, False, self.pid)
        if not self.hp:
            raise OSError("OpenProcess 失败 %d (pid=%d)" % (k32.GetLastError(), self.pid))
        self.buf = k32.VirtualAllocEx(self.hp, None, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_RW)
        if not self.buf:
            raise OSError("VirtualAllocEx 失败")

    def get(self, msg, wparam, struct):
        u.SendMessageW(self.hwnd, msg, wparam, self.buf)
        n = ctypes.c_size_t()
        k32.ReadProcessMemory(self.hp, ctypes.c_void_p(self.buf),
                              ctypes.byref(struct), ctypes.sizeof(struct), ctypes.byref(n))
        return struct

    def raw(self, nbytes):
        b = ctypes.create_string_buffer(nbytes)
        k32.ReadProcessMemory(self.hp, ctypes.c_void_p(self.buf), b, nbytes, None)
        return b.raw

    def close(self):
        if self.buf:
            k32.VirtualFreeEx(self.hp, ctypes.c_void_p(self.buf), 0, MEM_RELEASE)
        if self.hp:
            k32.CloseHandle(self.hp)


def buttons(hwnd):
    r = Remote(hwnd)
    r.hwnd = hwnd
    try:
        n = u.SendMessageW(hwnd, TB_BUTTONCOUNT, 0, 0)
        out = []
        for i in range(n):
            tb = r.get(TB_GETBUTTON, i, TBBUTTON())
            rc = r.get(TB_GETITEMRECT, i, RECT())
            cnt = u.SendMessageW(hwnd, TB_GETBUTTONTEXTW, tb.idCommand, r.buf)
            text = ""
            if cnt and cnt > 0:
                raw = r.raw(cnt * 2 + 2)
                text = raw[:cnt * 2].decode("utf-16-le", "ignore")
            out.append({"i": i, "id": tb.idCommand, "style": tb.fsStyle,
                        "state": tb.fsState, "rect": (rc.l, rc.t, rc.r, rc.b),
                        "text": text})
        return out
    finally:
        r.close()


def toolbars(main_hwnd):
    """列出所有可见 BCG 工具栏及其屏幕矩形。"""
    hits = []

    def walk(hw):
        ch = u.GetWindow(hw, 5)
        while ch:
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(ch, cls, 256)
            if cls.value.startswith("BCGToolBar"):
                rect = wt.RECT()
                u.GetWindowRect(ch, ctypes.byref(rect))
                w, h = rect.right - rect.left, rect.bottom - rect.top
                if w > 0 and h > 0:
                    hits.append({"hwnd": ch,
                                 "rect": (rect.left, rect.top, rect.right, rect.bottom)})
            walk(ch)
            ch = u.GetWindow(ch, 2)
    walk(main_hwnd)
    return hits
