# -*- coding: utf-8 -*-
"""常驻提权代理：只弹一次 UAC，之后靠文件队列收指令。

指令目录 out/q/cmd/*.json，结果目录 out/q/res/*.json。
每次循环写心跳 out/q/hb.txt。

指令格式：{"op": "verify", "file": "...", "out": "..."}
支持 op：
    verify  启动 Multisim 打开指定文件，点掉弹窗，截图，报告
    kill    杀掉所有 multisim.exe
    shot    对当前主窗口截图
    ping    仅回应
"""
import ctypes
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import guiauto as G

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"
Q = os.path.join(ROOT, "out", "q")
CMD = os.path.join(Q, "cmd")
RES = os.path.join(Q, "res")
HB = os.path.join(Q, "hb.txt")
SHOTS = os.path.join(ROOT, "out", "shots")
for d in (CMD, RES, SHOTS):
    os.makedirs(d, exist_ok=True)


def log(msg):
    with open(os.path.join(Q, "agent.log"), "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))


def child_texts(hwnd, limit=30):
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
            out.append({"cls": cls.value, "text": t[:160]})
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
    seen = []
    for _ in range(maxn):
        ds = G.visible_dialogs()
        if not ds:
            break
        d = ds[0]
        item = {"title": d["title"], "children": child_texts(d["hwnd"])}
        btn = G.u.GetDlgItem(d["hwnd"], 1)
        br = G.rect(btn) if btn else None
        if br:
            G.click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
            item["dismissed"] = True
        seen.append(item)
        time.sleep(wait)
    return seen


def op_verify(req):
    target = req["file"]
    if not os.path.isabs(target):
        target = os.path.join(ROOT, target)
    rep = {"target": target, "steps": []}

    def step(name, **kw):
        kw["step"] = name
        rep["steps"].append(kw)

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE, target], creationflags=0x00000008, close_fds=True)
    hw = find_main()
    if not hw:
        rep["opened"] = False
        rep["error"] = "主窗口没出来"
        return rep
    time.sleep(5.0)
    G.show(hw, 3)
    time.sleep(2.0)

    step("dialogs", n=len(dismiss()))
    titles = [x["title"] for x in G.find(cls="Multisim14.3")]
    step("window", hwnd=hw, titles=titles)
    time.sleep(2.5)
    late = dismiss()
    if late:
        step("late_dialogs", n=len(late), items=late)

    shot = req.get("shot") or os.path.join(SHOTS, "agent.png")
    if not os.path.isabs(shot):
        shot = os.path.join(ROOT, shot)
    try:
        G.screenshot(hw, shot)
        step("screenshot", path=shot)
    except Exception as e:
        step("screenshot", err=repr(e))

    base = os.path.splitext(os.path.basename(target))[0]
    rep["opened"] = any(base.lower() in (t or "").lower() for t in titles)
    rep["titles"] = titles
    rep["shot"] = shot
    if not req.get("keep"):
        subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    return rep


def handle(req):
    op = req.get("op", "ping")
    if op == "ping":
        return {"ok": True, "admin": bool(ctypes.windll.shell32.IsUserAnAdmin()),
                "pid": os.getpid()}
    if op == "kill":
        subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
        return {"ok": True}
    if op == "verify":
        return op_verify(req)
    return {"ok": False, "error": "未知 op %r" % op}


def main():
    log("agent 启动 pid=%d admin=%s" % (os.getpid(), ctypes.windll.shell32.IsUserAnAdmin()))
    while True:
        try:
            with open(HB, "w") as f:
                f.write("%d %s\n" % (os.getpid(), time.strftime("%H:%M:%S")))
            names = sorted(n for n in os.listdir(CMD) if n.endswith(".json"))
            for n in names:
                path = os.path.join(CMD, n)
                try:
                    req = json.load(open(path, encoding="utf-8"))
                except Exception:
                    time.sleep(0.3)
                    continue
                log("收到 %s -> %s" % (n, req.get("op")))
                try:
                    res = handle(req)
                except Exception:
                    res = {"ok": False, "error": traceback.format_exc()}
                json.dump(res, open(os.path.join(RES, n), "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                os.remove(path)
                log("完成 %s" % n)
        except Exception:
            log("循环异常 " + traceback.format_exc())
        time.sleep(0.4)


if __name__ == "__main__":
    main()
