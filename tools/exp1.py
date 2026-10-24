# -*- coding: utf-8 -*-
"""一次性提权任务：启动真实界面的 Multisim，打开样例，复制全部，dump 剪贴板格式。

为什么关心剪贴板：剪贴板不需要压缩。如果 Multisim 在剪贴板里放的是**明文 XML**，
那就能绕过 .ms14 的压缩格式——把 XML 放进剪贴板再 Ctrl+V，就等于凭空创建电路。

结果写到 out/exp1.json，剪贴板各格式的原始字节写到 out/clip2/。
"""
import ctypes
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
CLIP = os.path.join(OUT, "clip2")
RESULT = os.path.join(OUT, "exp1.json")
SHOTS = os.path.join(OUT, "shots")
os.makedirs(CLIP, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

report = {"steps": []}


def step(name, **kw):
    kw["step"] = name
    report["steps"].append(kw)
    print(name, kw, flush=True)


def main():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(2.0)
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    hw = None
    t0 = time.time()
    while time.time() - t0 < 90:
        time.sleep(0.8)
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            hw = ws[0]["hwnd"]
            break
    if not hw:
        step("launch", ok=False, err="窗口没出来")
        return
    step("launch", ok=True, hwnd=hw, rect=list(G.rect(hw)))
    G.show(hw, 3)
    time.sleep(2.5)
    ok, fg = G.foreground(hw)
    step("foreground", ok=ok, fg=fg)

    # 打开样例（真实界面下用键盘走"文件-打开"不可靠，直接用命令行参数重开更稳）
    sample = os.path.join(ROOT, "samples", "7812.ms12")
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE, sample], creationflags=0x00000008, close_fds=True)
    hw = None
    t0 = time.time()
    while time.time() - t0 < 90:
        time.sleep(0.8)
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            hw = ws[0]["hwnd"]
            break
    if not hw:
        step("open_sample", ok=False)
        return
    time.sleep(4.0)
    G.show(hw, 3)
    time.sleep(1.5)
    ok, fg = G.foreground(hw)
    step("open_sample", ok=True, title=[x["title"] for x in G.find(cls="Multisim14.3")], fg=ok)
    G.screenshot(hw, os.path.join(SHOTS, "exp1_open.png"))

    # 清空剪贴板，确认后面拿到的是 Multisim 放的
    G.u.OpenClipboard(None)
    G.u.EmptyClipboard()
    G.u.CloseClipboard()

    # 点一下画布中心，确保焦点在原理图上
    r = G.rect(hw)
    G.click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(0.5)
    step("click_canvas", ok=G.u.GetForegroundWindow() == hw)

    G.hotkey("ctrl", "a")
    time.sleep(0.8)
    G.hotkey("ctrl", "c")
    time.sleep(2.0)
    G.screenshot(hw, os.path.join(SHOTS, "exp1_after_copy.png"))

    got = G.clipboard_formats(CLIP, "copy")
    step("clipboard", n=len(got), formats=[
        {"fmt": f, "name": n, "size": s, "head": d[:64].hex(" ")} for f, n, s, d in got])

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    json.dump(report, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        report["error"] = traceback.format_exc()
        json.dump(report, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("ERROR", e, flush=True)
    finally:
        json.dump(report, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
