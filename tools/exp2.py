# -*- coding: utf-8 -*-
"""一次性提权任务 2：把 Multisim 的复制内容捞出来。

上一轮 Ctrl+A 成功了（截图里全选中），但 Ctrl+C 之后剪贴板是空的。
这次加几层保险：点画布拿焦点 → Ctrl+A → 等 → Ctrl+C → 多次重试读剪贴板；
还不行就试 Ctrl+Insert / 编辑菜单。

结果：out/exp2.json，剪贴板字节在 out/clip2/。
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
RESULT = os.path.join(OUT, "exp2.json")
SHOTS = os.path.join(OUT, "shots")
os.makedirs(CLIP, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

report = {"steps": []}


def step(name, **kw):
    kw["step"] = name
    report["steps"].append(kw)
    print(name, kw, flush=True)


def find_main(timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ws = G.find(cls="Multisim14.3")
        if ws and G.rect(ws[0]["hwnd"])[2] > 300:
            return ws[0]["hwnd"]
        time.sleep(0.8)
    return None


def dismiss_dialogs(maxn=12, wait=0.7):
    """把挡住流程的模态框（尤其是三个"数据库无法访问"）自己点掉。"""
    clicked = []
    for _ in range(maxn):
        ds = G.visible_dialogs()
        if not ds:
            break
        d = ds[0]
        msg = G.dlg_message(d["hwnd"])
        btn = G.u.GetDlgItem(d["hwnd"], 1)
        br = G.rect(btn) if btn else None
        if br:
            G.click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
        clicked.append({"title": d["title"], "msg": msg.replace("\r", " ")[:80]})
        time.sleep(wait)
    return clicked


def clip_retry(tag, tries=6):
    for i in range(tries):
        got = G.clipboard_formats(CLIP, tag)
        if got:
            return got
        time.sleep(0.6)
    return []


def main():
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    step("admin", is_admin=admin)
    if not admin:
        step("abort", why="没有管理员权限，数据库弹窗会挡住流程")
        return
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"], capture_output=True)
    time.sleep(2.0)
    sample = os.path.join(ROOT, "samples", "7812.ms12")
    subprocess.Popen([EXE, sample], creationflags=0x00000008, close_fds=True)
    hw = find_main()
    if not hw:
        step("launch", ok=False)
        return
    time.sleep(5.0)
    G.show(hw, 3)
    time.sleep(2.0)
    ok, fg = G.foreground(hw)
    step("launch", ok=True, hwnd=hw, rect=list(G.rect(hw)), fg=ok,
         title=[x["title"] for x in G.find(cls="Multisim14.3")])
    d1 = dismiss_dialogs()
    step("dialogs_after_launch", n=len(d1), items=d1)
    if d1:
        G.show(hw, 3)
        time.sleep(1.0)
        G.foreground(hw)

    # 点画布上某个空位（元件之外的空白），确保焦点在原理图
    r = G.rect(hw)
    G.click(r[0] + 300, r[1] + 480)
    time.sleep(0.6)
    step("click", fg_ok=G.u.GetForegroundWindow() == hw)

    G.hotkey("ctrl", "a")
    time.sleep(1.0)
    G.screenshot(hw, os.path.join(SHOTS, "exp2_selected.png"))

    # 清空剪贴板
    for _ in range(5):
        if G.u.OpenClipboard(None):
            G.u.EmptyClipboard()
            G.u.CloseClipboard()
            break
        time.sleep(0.3)

    G.hotkey("ctrl", "c")
    time.sleep(2.0)
    got = clip_retry("ctrlc")
    step("ctrl_c", n=len(got), formats=[{"fmt": f, "name": n, "size": s, "head": d[:48].hex(" ")}
                                        for f, n, s, d in got])

    if not got:
        # 备用 1：Ctrl+Insert
        G.hotkey("ctrl", "insert")
        time.sleep(2.0)
        got = clip_retry("ctrlins")
        step("ctrl_insert", n=len(got), formats=[{"fmt": f, "name": n, "size": s, "head": d[:48].hex(" ")}
                                                 for f, n, s, d in got])

    if not got:
        # 备用 2：菜单 编辑 -> 复制（Alt+E 打开编辑菜单）
        G.hotkey("alt", "e")
        time.sleep(0.8)
        G.screenshot(hw, os.path.join(SHOTS, "exp2_editmenu.png"))
        step("edit_menu", note="见 exp2_editmenu.png")

    # 再试一次粘贴，看剪贴板里是不是 Multisim 自己的私有格式
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
