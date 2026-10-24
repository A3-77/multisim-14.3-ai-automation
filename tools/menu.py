# -*- coding: utf-8 -*-
"""读 Multisim 菜单（MFC 自绘菜单栏，GetMenu 拿不到）。

思路：点开某个顶级菜单 → 找到 #32768 弹窗 → MN_GETHMENU 取 HMENU
→ 用标准 GetMenu* 接口枚举条目和命令 ID。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

u = ctypes.windll.user32
u.SendMessageW.restype = ctypes.c_ssize_t
u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u.GetMenuStringW.argtypes = [ctypes.c_void_p, wt.UINT, wt.LPWSTR, ctypes.c_int, wt.UINT]
u.GetSubMenu.restype = ctypes.c_void_p
u.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
u.GetMenuItemID.argtypes = [ctypes.c_void_p, ctypes.c_int]
u.GetMenuItemCount.argtypes = [ctypes.c_void_p]

MN_GETHMENU = 0x01E1
MF_BYPOSITION = 0x400
MF_STRING = 0x0


def popup_menu_hwnd():
    for w in __import__("guiauto").enum_windows():
        if w["cls"] == "#32768" and w["vis"]:
            return w["hwnd"]
    return None


def hmenu_of(hwnd):
    return u.SendMessageW(hwnd, MN_GETHMENU, 0, 0)


def text_of(hm, i):
    buf = ctypes.create_unicode_buffer(512)
    u.GetMenuStringW(hm, i, buf, 512, MF_BYPOSITION)
    return buf.value.replace("&", "")


def dump(hm, indent=0, maxdepth=2, path=""):
    n = u.GetMenuItemCount(hm)
    out = []
    for i in range(n):
        t = text_of(hm, i)
        cid = u.GetMenuItemID(hm, i)
        sub = u.GetSubMenu(hm, i)
        out.append({"i": i, "text": t, "id": cid, "sub": bool(sub),
                    "path": path + "/" + t})
        print("  " * indent + "%-32s id=%s%s" % (t, cid, "  [sub]" if sub else ""))
        if sub and indent < maxdepth:
            out += dump(sub, indent + 1, maxdepth, path + "/" + t)
    return out
