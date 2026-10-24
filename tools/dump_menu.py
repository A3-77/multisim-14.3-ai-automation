# -*- coding: utf-8 -*-
"""提权运行：启动 Multisim 并把完整菜单树（含命令 ID）dump 出来。

用途：
  1. 摸清 Multisim 到底有哪些命令（尤其看有没有"网表导入"这类捷径）
  2. 为 GUI 自动化拿到准确的命令 ID
产出 out/menu.json / out/menu.txt
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import guiauto as G

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
OUT = os.path.join(ROOT, "out")
u = ctypes.windll.user32
u.GetMenuStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p,
                             ctypes.c_int, ctypes.c_uint]

MENUBREAK = 0x80000000
MF_POPUP = 0x00000010


def item_text(hmenu, idx, bypos=True):
    buf = ctypes.create_unicode_buffer(256)
    flag = 0x400 if bypos else 0
    n = u.GetMenuStringW(hmenu, idx, buf, 256, flag)
    return buf.value.replace("&", "") if n else ""


def walk(hmenu, depth, path, out, maxdepth=3):
    if depth > maxdepth:
        return
    n = u.GetMenuItemCount(hmenu)
    for i in range(n):
        txt = item_text(hmenu, i)
        if not txt or txt == "-":
            continue
        sub = u.GetSubMenu(hmenu, i)
        if sub:
            out.append({"depth": depth, "path": path + [txt], "id": None})
            walk(sub, depth + 1, path + [txt], out, maxdepth)
        else:
            mid = u.GetMenuItemID(hmenu, i)
            if mid in (0, 0xFFFFFFFF):
                continue
            out.append({"depth": depth, "path": path + [txt], "id": mid})


def find_main(timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            return ws[0]["hwnd"]
        time.sleep(0.8)
    return None


def dismiss(maxn=15):
    for _ in range(maxn):
        ds = G.visible_dialogs()
        if not ds:
            return
        btn = G.u.GetDlgItem(ds[0]["hwnd"], 1)
        br = G.rect(btn) if btn else None
        if br:
            G.click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
        time.sleep(0.7)


def main():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    hw = find_main()
    if not hw:
        print("找不到主窗口", flush=True)
        return
    time.sleep(6.0)
    dismiss()

    hmenu = u.GetMenu(hw)
    print("hmenu =", hmenu, flush=True)
    items = []
    if hmenu:
        walk(hmenu, 0, [], items)

    lines = []
    for it in items:
        ind = "  " * it["depth"]
        if it["id"] is None:
            lines.append("%s[%s]" % (ind, it["path"][-1]))
        else:
            lines.append("%s%s  <%d>" % (ind, it["path"][-1], it["id"]))
    txt = "\n".join(lines)
    open(os.path.join(OUT, "menu.txt"), "w", encoding="utf-8").write(txt)
    json.dump(items, open(os.path.join(OUT, "menu.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(txt[:6000], flush=True)
    print("\n共 %d 项" % len(items), flush=True)
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
