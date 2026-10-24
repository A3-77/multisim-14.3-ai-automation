# -*- coding: utf-8 -*-
"""提权助手：以管理员身份常驻，替我们做"需要管理员才能做"的事。

为什么要提权：这台机器上 Multisim.exe 被设成了"以管理员身份运行"（为了能打开元件库），
普通权限的进程既启动不了它，也连不上它的 COM。

指令写在 out/ecmd.json，结果写在 out/eres.json。
    {"op":"open","path":"...ms14"}   用 COM 打开并报告元件数（25 秒超时，防弹窗卡死）
    {"op":"reset"}                   杀掉 Multisim 并断开，重新开始
    {"op":"dismiss"}                 点掉所有可见的模态框
    {"op":"shot","name":"x"}         截 Multisim 主窗口
    {"op":"wins"}                    列出 Multisim 的窗口
    {"op":"eval","code":"..."}       执行任意代码（内部调试用）
    {"op":"quit"}
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

OUT = os.path.join(ROOT, "out")
CMD = os.path.join(OUT, "ecmd.json")
RES = os.path.join(OUT, "eres.json")
HB = os.path.join(OUT, "ehb.txt")
LOG = os.path.join(OUT, "elev.log")
SHOTS = os.path.join(OUT, "shots")
os.makedirs(SHOTS, exist_ok=True)

STATE = {"app": None}


def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), " ".join(str(x) for x in a)))


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def reset_multisim():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(1.5)
    STATE["app"] = None


def call_with_timeout(fn, timeout):
    box = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        return None, "卡住（>%ds，多半是弹了模态框）" % timeout
    if "e" in box:
        return None, repr(box["e"])
    return box.get("v"), None


def main():
    open(LOG, "w", encoding="utf-8").close()
    log("提权助手启动 admin=%s pid=%s" % (is_admin(), os.getpid()))
    if not is_admin():
        log("!! 不是管理员，退出")
        return

    import msc
    import guiauto as G
    import pythoncom
    pythoncom.CoInitialize()

    last = 0.0
    while True:
        with open(HB, "w") as f:
            f.write(str(time.time()))
        try:
            if os.path.exists(CMD):
                m = os.path.getmtime(CMD)
                if m != last:
                    last = m
                    cmd = json.load(open(CMD, encoding="utf-8"))
                    log("执行", json.dumps(cmd, ensure_ascii=False)[:200])
                    op = cmd.get("op")
                    try:
                        if op == "quit":
                            log("退出")
                            return
                        elif op == "reset":
                            reset_multisim()
                            res = {"ok": True}
                        elif op == "dismiss":
                            n = 0
                            for _ in range(8):
                                ds = G.visible_dialogs()
                                if not ds:
                                    break
                                d = ds[0]
                                btn = G.u.GetDlgItem(d["hwnd"], 1)
                                br = G.rect(btn) if btn else None
                                if br:
                                    G.click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
                                n += 1
                                time.sleep(0.7)
                            res = {"ok": True, "clicked": n}
                        elif op == "open":
                            def do_open():
                                pythoncom.CoInitialize()
                                if STATE["app"] is None:
                                    STATE["app"] = msc.Multisim()
                                    log("COM 已连接", STATE["app"].version)
                                cir = STATE["app"].open(cmd["path"])
                                return {"ok": True, "name": cir.name, "n": len(cir.components()),
                                        "file": cir.file, "last_err": cir.last_error}
                            v, err = call_with_timeout(do_open, cmd.get("timeout", 25))
                            res = v if v else {"ok": False, "err": err}
                            if err and "卡住" in str(err):
                                log("open 卡住，重置 Multisim")
                                reset_multisim()
                        elif op == "new":
                            def do_new():
                                pythoncom.CoInitialize()
                                if STATE["app"] is None:
                                    STATE["app"] = msc.Multisim()
                                cir = STATE["app"].new()
                                return {"ok": True, "name": cir.name, "n": len(cir.components())}
                            v, err = call_with_timeout(do_new, cmd.get("timeout", 25))
                            res = v if v else {"ok": False, "err": err}
                        elif op == "shot":
                            ws = G.find(cls="Multisim14.3") or G.find(cls="LVFrame")
                            if not ws:
                                res = {"ok": False, "err": "没有 Multisim 窗口"}
                            else:
                                G.show(ws[0]["hwnd"], 3)
                                time.sleep(0.8)
                                p, ok, size = G.screenshot(ws[0]["hwnd"],
                                                           os.path.join(SHOTS, cmd.get("name", "s") + ".png"))
                                res = {"ok": True, "shot": p, "size": size}
                        elif op == "wins":
                            pids = G.multisim_pids()
                            res = {"ok": True, "wins": [
                                {"cls": x["cls"], "title": x["title"], "vis": x["vis"],
                                 "rect": list(G.rect(x["hwnd"]))}
                                for x in G.enum_windows() if x["pid"] in pids]}
                        elif op == "eval":
                            g = {"msc": msc, "G": G, "os": os, "time": time, "sys": sys,
                                 "app": STATE["app"], "result": None, "ROOT": ROOT, "OUT": OUT,
                                 "SHOTS": SHOTS, "subprocess": subprocess, "json": json,
                                 "threading": threading}
                            exec(cmd["code"], g)
                            STATE["app"] = g.get("app", STATE["app"])
                            r = g.get("result")
                            try:
                                json.dumps(r)
                            except Exception:
                                r = repr(r)
                            res = {"ok": True, "result": r}
                        else:
                            res = {"ok": False, "err": "未知指令"}
                    except Exception as e:
                        res = {"ok": False, "err": repr(e)}
                    log("结果", json.dumps(res, ensure_ascii=False)[:300])
                    json.dump(res, open(RES, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception as e:
            log("循环异常", repr(e))
        time.sleep(0.2)


if __name__ == "__main__":
    main()
