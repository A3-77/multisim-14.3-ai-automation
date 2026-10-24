# -*- coding: utf-8 -*-
"""常驻驱动进程：保持一个真实 UI 的 Multisim 实例，从 out/cmd.json 取指令执行。

指令格式（JSON，每次写入即触发执行）：
  {"op":"shot","name":"03_dlg"}
  {"op":"key","keys":["ctrl","o"]}
  {"op":"type","text":"C:\\path\\a.ms12"}
  {"op":"click","x":100,"y":200,"rel":true,"double":false,"button":"left"}
  {"op":"drag","x1":..,"y1":..,"x2":..,"y2":..}
  {"op":"move","x":..,"y":..}
  {"op":"clip","tag":"sel"}
  {"op":"info"}
  {"op":"kill"}         关掉 Multisim
  {"op":"relaunch"}     重启 Multisim
  {"op":"exit"}         退出驱动进程

结果写到 out/res.json，日志追加到 out/drv.log。
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guiauto as G

OUT = os.path.join(ROOT, "out")
SHOTS = os.path.join(OUT, "shots")
CMD = os.path.join(OUT, "cmd.json")
RES = os.path.join(OUT, "res.json")
LOG = os.path.join(OUT, "drv.log")
HB = os.path.join(OUT, "hb.txt")
EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\multisim.exe"

os.makedirs(SHOTS, exist_ok=True)


def log(*a):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), " ".join(str(x) for x in a))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main_window():
    ws = G.find(cls="Multisim14.3")
    return ws[0]["hwnd"] if ws else None


def launch(timeout=60, reuse=True):
    hw = main_window()
    if reuse and hw:
        r = G.rect(hw)
        if r[2] - r[0] > 300:
            G.show(hw, 3)
            time.sleep(0.8)
            G.foreground(hw)
            time.sleep(0.3)
            log("复用已运行的 Multisim hwnd=%s" % hw)
            return hw
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    t0 = time.time()
    hw = None
    while time.time() - t0 < timeout:
        time.sleep(0.6)
        hw = main_window()
        if hw:
            r = G.rect(hw)
            if r[2] - r[0] > 300:
                break
    if not hw:
        raise RuntimeError("Multisim 没起来")
    time.sleep(2.0)
    G.show(hw, 3)
    time.sleep(1.0)
    G.foreground(hw)
    time.sleep(0.5)
    return hw


def execute(cmd):
    op = cmd.get("op")
    hw = main_window()
    if op == "relaunch":
        hw = launch()
        return {"ok": True, "hwnd": hw, "rect": G.rect(hw)}
    if op == "eval":
        g = {"G": G, "hw": hw, "os": os, "time": time, "sys": sys,
             "ROOT": ROOT, "OUT": OUT, "SHOTS": SHOTS, "subprocess": subprocess,
             "main_window": main_window, "result": None, "json": json}
        exec(cmd["code"], g)
        res = g.get("result")
        try:
            json.dumps(res)
        except Exception:
            res = repr(res)
        return {"ok": True, "result": res}
    if op == "wins":
        pids = G.multisim_pids()
        out = []
        for x in G.enum_windows():
            if x["pid"] in pids:
                out.append({"hwnd": x["hwnd"], "cls": x["cls"], "title": x["title"],
                            "vis": x["vis"], "rect": G.rect(x["hwnd"])})
        return {"ok": True, "wins": out}
    if op == "shotwin":
        cands = [x for x in G.enum_windows()
                 if x["cls"] == cmd.get("cls", "Multisim14.3")
                 and (not cmd.get("title") or cmd["title"].lower() in x["title"].lower())]
        if not cands:
            return {"ok": False, "err": "找不到窗口 %s" % cmd.get("cls")}
        target = cands[cmd.get("idx", 0)]["hwnd"]
        path = os.path.join(SHOTS, cmd.get("name", "win") + ".png")
        p, ok, size = G.screenshot(target, path)
        return {"ok": True, "shot": p, "size": size, "hwnd": target}
    if op == "focuswin":
        cands = [x for x in G.enum_windows()
                 if x["cls"] == cmd.get("cls") and (not cmd.get("title") or cmd["title"].lower() in x["title"].lower())]
        if not cands:
            return {"ok": False, "err": "找不到窗口"}
        target = cands[cmd.get("idx", 0)]["hwnd"]
        return {"ok": True, "fg": G.foreground(target), "hwnd": target}
    if op == "kill":
        subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
        return {"ok": True}
    if hw is None:
        return {"ok": False, "err": "Multisim 窗口不存在"}
    if not G.foreground(hw):
        log("警告：拿不到前台")

    if op == "info":
        r = G.rect(hw)
        return {"ok": True, "hwnd": hw, "rect": r, "fg": G.foreground(hw)[0],
                "pids": sorted(G.multisim_pids())}
    if op == "shot":
        name = cmd.get("name", "shot")
        path = os.path.join(SHOTS, name + ".png")
        p, ok, size = G.screenshot(hw, path)
        return {"ok": True, "shot": p, "size": size, "printwindow": ok}
    if op == "key":
        G.hotkey(*cmd["keys"])
        return {"ok": True}
    if op == "type":
        G.type_text(cmd["text"])
        return {"ok": True}
    if op == "click":
        r = G.rect(hw)
        x, y = cmd["x"], cmd["y"]
        if cmd.get("rel"):
            x += r[0]
            y += r[1]
        G.click(x, y, cmd.get("button", "left"), cmd.get("double", False))
        return {"ok": True, "abs": [x, y]}
    if op == "move":
        r = G.rect(hw)
        x, y = cmd["x"], cmd["y"]
        if cmd.get("rel"):
            x += r[0]
            y += r[1]
        G.u.SetCursorPos(int(x), int(y))
        return {"ok": True, "abs": [x, y]}
    if op == "drag":
        r = G.rect(hw)
        x1, y1, x2, y2 = cmd["x1"], cmd["y1"], cmd["x2"], cmd["y2"]
        if cmd.get("rel"):
            x1 += r[0]; y1 += r[1]; x2 += r[0]; y2 += r[1]
        G.drag(x1, y1, x2, y2, steps=cmd.get("steps", 18))
        return {"ok": True}
    if op == "clip":
        got = G.clipboard_formats(os.path.join(OUT, "clip"), cmd.get("tag", "c"))
        return {"ok": True, "formats": [{"fmt": f, "name": n, "size": s, "head": d[:80].hex()} for f, n, s, d in got]}
    return {"ok": False, "err": "未知指令 " + str(op)}


def main():
    open(LOG, "w", encoding="utf-8").close()
    log("驱动启动")
    try:
        hw = launch()
        log("Multisim 就绪 hwnd=%s rect=%s" % (hw, G.rect(hw)))
        G.screenshot(hw, os.path.join(SHOTS, "00_launch.png"))
        log("初始截图完成")
    except Exception as e:
        log("启动失败", repr(e))

    last_mtime = 0.0
    while True:
        with open(HB, "w") as f:
            f.write(str(time.time()))
        try:
            if os.path.exists(CMD):
                m = os.path.getmtime(CMD)
                if m != last_mtime:
                    last_mtime = m
                    with open(CMD, encoding="utf-8") as f:
                        cmd = json.load(f)
                    log("执行", cmd)
                    try:
                        res = execute(cmd)
                    except Exception as e:
                        res = {"ok": False, "err": repr(e)}
                    log("结果", json.dumps(res, ensure_ascii=False)[:400])
                    with open(RES, "w", encoding="utf-8") as f:
                        json.dump(res, f, ensure_ascii=False)
                    if cmd.get("op") == "exit":
                        log("按指令退出")
                        return
        except Exception as e:
            log("循环异常", repr(e))
        time.sleep(0.25)


if __name__ == "__main__":
    main()
