# -*- coding: utf-8 -*-
"""一次性提权任务 3：搞清"复制"到底走没走系统剪贴板，并把菜单/快捷键表捞出来。

1) 提权启动 Multisim，打开 7812
2) Ctrl+A -> Ctrl+C，然后诊断剪贴板（OpenClipboard 是否成功、owner 是谁）
3) 扫内存，把菜单栏/快捷键表/命令名表 dump 到 out/mem3/
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
import memscan

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
OUT = os.path.join(ROOT, "out")
MEM3 = os.path.join(OUT, "mem3")
RESULT = os.path.join(OUT, "exp3.json")
SHOTS = os.path.join(OUT, "shots")
os.makedirs(MEM3, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

report = {"steps": []}
u = G.u
k32 = ctypes.windll.kernel32


def step(name, **kw):
    kw["step"] = name
    report["steps"].append(kw)
    print(name, json.dumps(kw, ensure_ascii=False)[:400], flush=True)


def dismiss_dialogs(maxn=12, wait=0.7):
    clicked = []
    for _ in range(maxn):
        ds = G.visible_dialogs()
        if not ds:
            break
        d = ds[0]
        msg = G.dlg_message(d["hwnd"])
        btn = u.GetDlgItem(d["hwnd"], 1)
        br = G.rect(btn) if btn else None
        if br:
            G.click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
        clicked.append(msg.replace("\r", " ")[:80])
        time.sleep(wait)
    return clicked


def clip_diag():
    ok = bool(u.OpenClipboard(None))
    info = {"open_ok": ok}
    if ok:
        try:
            info["owner"] = u.GetClipboardOwner()
            fmts = []
            f = 0
            while True:
                f = u.EnumClipboardFormats(f)
                if f == 0:
                    break
                nm = ctypes.create_unicode_buffer(256)
                n = u.GetClipboardFormatNameW(f, nm, 256)
                fmts.append({"fmt": f, "name": nm.value if n else "std%d" % f})
            info["formats"] = fmts
        finally:
            u.CloseClipboard()
    info["open_window"] = u.GetOpenClipboardWindow()
    return info


def main():
    step("admin", is_admin=bool(ctypes.windll.shell32.IsUserAnAdmin()))
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(2.0)
    subprocess.Popen([EXE, os.path.join(ROOT, "samples", "7812.ms12")],
                     creationflags=0x00000008, close_fds=True)
    hw = None
    t0 = time.time()
    while time.time() - t0 < 90:
        time.sleep(0.8)
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            hw = ws[0]["hwnd"]
            break
    if not hw:
        step("launch", ok=False)
        return
    time.sleep(5.0)
    G.show(hw, 3)
    time.sleep(1.5)
    G.foreground(hw)
    time.sleep(0.5)
    step("launch", ok=True, title=[x["title"] for x in G.find(cls="Multisim14.3")])
    step("dialogs", items=dismiss_dialogs())

    r = G.rect(hw)
    G.click(r[0] + 300, r[1] + 470)
    time.sleep(0.5)
    G.hotkey("ctrl", "a")
    time.sleep(0.8)
    G.screenshot(hw, os.path.join(SHOTS, "exp3_selected.png"))

    for _ in range(5):
        if u.OpenClipboard(None):
            u.EmptyClipboard()
            u.CloseClipboard()
            break
        time.sleep(0.3)

    G.hotkey("ctrl", "c")
    time.sleep(2.5)
    step("clip_after_ctrlc", **clip_diag())

    # 内存扫描：菜单栏 / 快捷键 / 命令名
    pids = sorted(G.multisim_pids())
    if pids:
        regions, nreg = memscan.read_regions(pids[0])
        step("memscan", pid=pids[0], regions=nreg, read=len(regions))
        wanted = {b"<MenuBar": "menubar", b"<Accelerator": "accel", b"IDS_FILEMENU": "ids",
                  b"&ASC&Place": "place"}
        found = []
        for key, tag in wanted.items():
            for base, data in regions:
                i = data.find(key)
                if i < 0:
                    continue
                s = max(0, i - 2000)
                e = min(len(data), i + 120000)
                chunk = data[s:e]
                p = os.path.join(MEM3, "%s_%x.bin" % (tag, base + i))
                open(p, "wb").write(chunk)
                found.append({"tag": tag, "len": len(chunk), "file": os.path.basename(p)})
                break
        step("mem_dump", n=len(found), files=found)

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        report["error"] = traceback.format_exc()
    finally:
        json.dump(report, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
