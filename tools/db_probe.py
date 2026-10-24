# -*- coding: utf-8 -*-
"""判断 Multisim 的元件数据库能不能打开。

流程：清场 -> 启动真实 UI 的 Multisim -> Ctrl+W 打开"选择一个元器件"
     -> 看有没有"数据库无法访问"的弹窗 -> 报告结论
"""
import ctypes
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
DBDIRS = [r"C:\ProgramData\National Instruments\Circuit Design Suite\14.3\database",
          os.path.join(os.environ["APPDATA"], "National Instruments", "Circuit Design Suite", "14.3", "database")]


def clean():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(2.5)
    removed = []
    for d in DBDIRS:
        for f in glob.glob(os.path.join(d, "*.ldb")):
            try:
                os.remove(f)
                removed.append(f)
            except OSError:
                pass
    return removed


def main():
    print("[1] 清理:", clean())
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    hw = None
    t0 = time.time()
    while time.time() - t0 < 60:
        time.sleep(0.7)
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            hw = ws[0]["hwnd"]
            break
    if not hw:
        print("!! Multisim 没起来")
        return 1
    print("[2] 窗口就绪", hw, G.rect(hw))
    G.show(hw, 3)
    time.sleep(2.5)
    G.foreground(hw)
    time.sleep(0.5)

    print("[3] Ctrl+W")
    G.hotkey("ctrl", "w")
    time.sleep(3.5)

    ds = G.visible_dialogs()
    print("[4] 可见对话框 %d 个" % len(ds))
    verdict = "unknown"
    for d in ds:
        msg = G.dlg_message(d["hwnd"])
        print("    -", d["title"], "|", msg.replace("\r", " ")[:150])
        if "数据库" in msg:
            verdict = "db_fail"
    if not ds:
        verdict = "db_ok"

    # 看看"选择一个元器件"对话框在不在
    cand = [x for x in G.enum_windows() if "元器件" in x["title"]]
    print("[5] 选择元器件对话框:", [(c["title"], c["vis"], G.rect(c["hwnd"])) for c in cand])
    if cand and cand[0]["vis"]:
        verdict = "db_ok"
        G.screenshot(cand[0]["hwnd"], os.path.join(ROOT, "out", "shots", "10_selectdlg.png"))

    G.screenshot_screen(os.path.join(ROOT, "out", "shots", "11_screen.png"))
    print("[6] 结论:", verdict)
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
