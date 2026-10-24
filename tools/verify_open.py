# -*- coding: utf-8 -*-
"""提权验证：把指定文件丢给 Multisim，看它能不能正常打开。

用法（经 oneshot 提权执行）：
    python tools/oneshot.py tools/verify_open.py out/verify.json out/own_blank.ms14

产出 out/verify.json + out/shots/verify.png
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
SHOTS = os.path.join(OUT, "shots")
os.makedirs(SHOTS, exist_ok=True)

target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "own_blank.ms14")
result = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUT, "verify.json")
if not os.path.isabs(target):
    target = os.path.join(ROOT, target)
if not os.path.isabs(result):
    result = os.path.join(ROOT, result)

report = {"target": target, "steps": []}


def step(name, **kw):
    kw["step"] = name
    report["steps"].append(kw)
    print(name, kw, flush=True)


def child_texts(hwnd, limit=40):
    """枚举对话框里所有子控件的文字，用来判断弹了什么错误。"""
    out = []
    u = G.u
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(h, _):
        buf = ctypes.create_unicode_buffer(512)
        u.GetWindowTextW(h, buf, 512)
        cls = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(h, cls, 128)
        t = buf.value.strip()
        if t:
            out.append({"cls": cls.value, "text": t[:200]})
        return True

    u.EnumChildWindows(hwnd, CB(cb), 0)
    return out[:limit]


def find_main(timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            return ws[0]["hwnd"]
        time.sleep(0.8)
    return None


def dismiss(maxn=15, wait=0.8):
    """点掉模态框，但把内容记下来。"""
    seen = []
    for _ in range(maxn):
        ds = G.visible_dialogs()
        if not ds:
            break
        d = ds[0]
        item = {"title": d["title"], "children": child_texts(d["hwnd"])}
        btn = G.u.GetDlgItem(d["hwnd"], 1)
        br = G.rect(btn) if btn else None
        item["dismissed"] = bool(br)
        if br:
            G.click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
        seen.append(item)
        time.sleep(wait)
    return seen


def main():
    step("admin", is_admin=bool(ctypes.windll.shell32.IsUserAnAdmin()))
    step("target", exists=os.path.exists(target),
         size=os.path.getsize(target) if os.path.exists(target) else 0)

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(2.0)

    subprocess.Popen([EXE, target], creationflags=0x00000008, close_fds=True)
    hw = find_main()
    if not hw:
        step("launch", ok=False)
        return
    time.sleep(5.0)
    G.show(hw, 3)
    time.sleep(2.0)

    dialogs = dismiss()
    step("dialogs", n=len(dialogs), items=dialogs)

    titles = [x["title"] for x in G.find(cls="Multisim14.3")]
    step("window", hwnd=hw, rect=list(G.rect(hw)), titles=titles)

    # 再等一会儿，让可能延迟出现的错误框冒出来
    time.sleep(3.0)
    late = dismiss()
    if late:
        step("late_dialogs", n=len(late), items=late)

    shot = os.path.join(SHOTS, "verify.png")
    try:
        G.screenshot(hw, shot)
        step("screenshot", path=shot, ok=os.path.exists(shot))
    except Exception as e:
        step("screenshot", ok=False, err=repr(e))

    base = os.path.splitext(os.path.basename(target))[0]
    opened = any(base.lower() in (t or "").lower() for t in titles)
    report["opened"] = opened
    step("verdict", opened=opened, base=base, titles=titles)

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        report["error"] = traceback.format_exc()
        print(report["error"], flush=True)
    finally:
        json.dump(report, open(result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
