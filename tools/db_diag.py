# -*- coding: utf-8 -*-
"""Multisim 14.3 元件数据库可用性诊断 / 复现工具。

只观察，不修系统：不改注册表、不改配置、不删文件（除了按需清理 .ldb 锁）。

做四件事
--------
1. 快照：版本号、系统区域、数据库文件（大小/时间/哈希）、.ldb 锁、Jet 注册表、进程。
2. 启动：`direct`（直接跑 exe，等价于双击）或 `com`（等价于 v0.8 的
   Dispatch+Connect），记录 PID / 启动时间 / 可执行文件路径。
3. 抓弹窗：轮询顶层窗口，把每个 `#32770` 对话框里的**全部控件文本**dump 出来
   —— 这就是"数据库报错的完整文字"，不靠猜。抓完可自动点"确定"，看后续是否
   连环弹 Corporate / Master。
4. 验元件库：可选按 Ctrl+W 打开"选择一个元器件"，截图并数一下列表项，判断
   库到底是不是空的。

用法
----
    python tools/db_diag.py --tag cold1 --mode direct --ctrlw
    python tools/db_diag.py --tag com1  --mode com
    python tools/db_diag.py --tag cold2 --mode direct --clean-ldb

产物
----
    out/dbdiag/<时间戳>_<tag>/
        snapshot.json     环境快照
        timeline.jsonl    逐秒事件（窗口出现 / 弹窗 / 进程消失）
        report.md         人读的报告
        shots/*.png       截图
"""
import argparse
import ctypes
import ctypes.wintypes as w
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import guiauto as G  # noqa: E402

EXE = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\Multisim.exe"
PROGID = "MultisimInterface.MultisimApp"

DBDIR_PROGRAMDATA = r"C:\ProgramData\National Instruments\Circuit Design Suite\14.3\database"
DBDIR_APPDATA = os.path.join(os.environ.get("APPDATA", ""), "National Instruments",
                             "Circuit Design Suite", "14.3", "database")
DBDIR_INSTALL = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\database"

u = ctypes.windll.user32
WM_GETTEXT = 0x000D
BM_CLICK = 0x00F5


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------
def _sha1_head(path, n=1024 * 1024):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            h.update(f.read(n))
        return h.hexdigest()[:16]
    except OSError as e:
        return "ERR:%s" % e


def db_files():
    out = []
    for d in (DBDIR_PROGRAMDATA, DBDIR_APPDATA, DBDIR_INSTALL):
        if not os.path.isdir(d):
            out.append({"dir": d, "exists": False})
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            st = os.stat(p)
            out.append({
                "dir": d, "name": name, "path": p,
                "bytes": st.st_size,
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                "sha1_head": _sha1_head(p),
            })
    return out


def ldb_files():
    hits = []
    for d in (DBDIR_PROGRAMDATA, DBDIR_APPDATA):
        hits += glob.glob(os.path.join(d, "*.ldb"))
    return hits


def file_version(path):
    try:
        import win32api
        info = win32api.GetFileVersionInfo(path, "\\")
        ms, ls = info["FileVersionMS"], info["FileVersionLS"]
        return "%d.%d.%d.%d" % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except Exception:
        return None


def jet_registry():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\WOW6432Node\Microsoft\Jet\4.0\Engines\Jet 4.0")
        out = {}
        i = 0
        while True:
            try:
                n, v, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            out[n] = v
            i += 1
        winreg.CloseKey(k)
        return out
    except Exception as e:
        return {"__error__": str(e)}


def snapshot(mode):
    import platform
    snap = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "python": sys.version.split()[0],
        "bits": 32 if sys.maxsize < 2 ** 32 else 64,
        "windows": platform.platform(),
        "os_build": platform.version(),
        "locale_LCID": ctypes.windll.kernel32.GetSystemDefaultLCID(),
        "multisim_exe": EXE,
        "multisim_exe_exists": os.path.isfile(EXE),
        "multisim_file_version": file_version(EXE) if os.path.isfile(EXE) else None,
        "db_files": db_files(),
        "ldb_before": ldb_files(),
        "jet_registry": jet_registry(),
        "multisim_pids_before": sorted(G.multisim_pids()),
    }
    return snap


# ---------------------------------------------------------------------------
# 窗口 / 对话框
# ---------------------------------------------------------------------------
def dump_children(hwnd):
    """递归 dump 一个窗口下所有子控件的 (class, ctrl_id, text)。"""
    items = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(h, lp):
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, cls, 256)
        buf = ctypes.create_unicode_buffer(8192)
        u.SendMessageW(h, WM_GETTEXT, 8192, buf)
        cid = u.GetDlgCtrlID(h)
        if buf.value.strip():
            items.append({"cls": cls.value, "id": cid, "text": buf.value})
        return True

    u.EnumChildWindows(hwnd, cb, 0)
    return items


def dialog_text(hwnd):
    """把对话框里所有可见文本拼起来（去重、保序）。"""
    seen, parts = set(), []
    for it in dump_children(hwnd):
        t = it["text"].strip()
        if t and t not in seen:
            seen.add(t)
            parts.append(t)
    return parts


DB_WORDS = ("数据库", "Database", "database", "Master", "Corporate", "User Database")


def is_db_error(title, parts):
    """区分"数据库报错弹窗"和启动闪屏。

    闪屏特征：标题就是 Multisim、正文里有"版本 14.3.0"和版权行。
    数据库报错特征：正文里出现 数据库/Database 且带 cannot be accessed 之类。
    """
    blob = (title or "") + " " + " ".join(parts)
    if "版本 14.3" in blob and "版权所有" in blob:
        return False
    low = blob.lower()
    return any(w.lower() in low for w in DB_WORDS) or "cannot be accessed" in low


def click_ok(hwnd):
    """点对话框里的 确定 / OK / 是。"""
    wants = ("确定", "OK", "&OK", "是", "&Yes")
    for it in dump_children(hwnd):
        if it["cls"] == "Button" and it["text"].strip() in wants:
            u.SendMessageW(u.GetDlgItem(hwnd, it["id"]), BM_CLICK, 0, 0)
            return it["text"].strip()
    # 兜底：直接回车
    G.press(0x0D)
    return "<Enter>"


def dialogs_of(pid):
    return [x for x in G.enum_windows()
            if x["cls"] == "#32770" and x["vis"] and x["pid"] == pid]


def main_window(pid):
    best = None
    for x in G.enum_windows():
        if x["pid"] != pid or not x["vis"]:
            continue
        if x["cls"].startswith("Multisim"):
            r = G.rect(x["hwnd"])
            area = max(0, r[2] - r[0]) * max(0, r[3] - r[1])
            if area > 300 * 300 and (best is None or area > best[0]):
                best = (area, x)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
def launch(mode):
    """返回 (pid, 说明)。com 模式走 Dispatch+Connect，和 v0.8 完全一致。"""
    for p in G.multisim_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
    time.sleep(1.5)

    t0 = time.time()
    if mode == "com":
        import win32com.client
        app = win32com.client.Dispatch(PROGID)
        app.Connect()
        time.sleep(0.5)
        try:
            exe = app.ExecutablePath
        except Exception:
            exe = "?"
        pids = sorted(G.multisim_pids())
        return (pids[-1] if pids else -1), {"how": "Dispatch+Connect", "exe_reported": exe,
                                            "launch_s": round(time.time() - t0, 2)}
    # direct
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    pid = -1
    while time.time() - t0 < 20:
        pids = sorted(G.multisim_pids())
        if pids:
            pid = pids[-1]
            break
        time.sleep(0.1)
    return pid, {"how": "Popen(exe)", "launch_s": round(time.time() - t0, 2)}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(args):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(ROOT, "out", "dbdiag", "%s_%s" % (stamp, args.tag))
    os.makedirs(os.path.join(outdir, "shots"), exist_ok=True)
    tl_path = os.path.join(outdir, "timeline.jsonl")
    tl = open(tl_path, "w", encoding="utf-8")

    def ev(kind, **kw):
        rec = {"t": round(time.time() - T0, 2), "kind": kind}
        rec.update(kw)
        tl.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tl.flush()
        print("  [%6.2fs] %-14s %s" % (rec["t"], kind,
                                       json.dumps(kw, ensure_ascii=False)[:150]))

    T0 = time.time()
    print("[1] 环境快照 …")
    snap = snapshot(args.mode)
    if args.clean_ldb:
        removed = []
        for f in snap["ldb_before"]:
            try:
                os.remove(f)
                removed.append(f)
            except OSError as e:
                removed.append("%s (失败: %s)" % (f, e))
        snap["ldb_removed"] = removed
        print("    清理 .ldb:", removed or "无")

    print("[2] 启动 Multisim (%s) …" % args.mode)
    pid, linfo = launch(args.mode)
    snap["launch"] = linfo
    snap["pid"] = pid
    ev("launch", pid=pid, **linfo)
    if pid <= 0:
        print("!! 没拿到 PID，放弃")
        return 2

    print("[3] 盯窗口 / 抓弹窗（最长 %ds）…" % args.wait)
    seen_dlg = {}
    seen_dialogs_text = []
    main_win = None
    proc_dead_at = None
    ok_clicked = 0
    t_start = time.time()
    while time.time() - t_start < args.wait:
        if pid not in G.multisim_pids():
            proc_dead_at = round(time.time() - T0, 2)
            ev("process_gone", pid=pid)
            break

        for d in dialogs_of(pid):
            h = d["hwnd"]
            if h in seen_dlg:
                continue
            txt = dialog_text(h)
            shot = os.path.join(outdir, "shots", "dlg_%d_%s.png"
                                % (len(seen_dlg) + 1, time.strftime("%H%M%S")))
            try:
                G.screenshot(h, shot)
            except Exception:
                shot = None
            seen_dlg[h] = {"title": d["title"], "text": txt, "shot": shot,
                           "at": round(time.time() - T0, 2),
                           "is_db_error": is_db_error(d["title"], txt)}
            seen_dialogs_text.append({"title": d["title"], "text": txt,
                                      "is_db_error": is_db_error(d["title"], txt)})
            ev("dialog", title=d["title"], text=txt, shot=shot)
            # 只对"数据库报错"弹窗按确定；闪屏绝不碰，否则会打断初始化
            if args.auto_ok and ok_clicked < args.max_ok and is_db_error(d["title"], txt):
                b = click_ok(h)
                ok_clicked += 1
                ev("dialog_ok", button=b)

        if main_win is None:
            mw = main_window(pid)
            if mw:
                main_win = mw
                r = G.rect(mw["hwnd"])
                ev("main_window", hwnd=mw["hwnd"], cls=mw["cls"],
                   size=[r[2] - r[0], r[3] - r[1]])
        time.sleep(0.25)

    if main_win is None and proc_dead_at is None:
        mw = main_window(pid)
        if mw:
            main_win = mw

    # ---- 元件库实测 ----
    lib_result = None
    if args.ctrlw and main_win and pid in G.multisim_pids():
        print("[4] Ctrl+W 打开元件选择窗口 …")
        G.show(main_win["hwnd"], 3)
        time.sleep(0.8)
        G.foreground(main_win["hwnd"])
        time.sleep(0.4)
        G.hotkey("ctrl", "w")
        time.sleep(args.ctrlw_wait)

        cands = [x for x in G.enum_windows()
                 if x["pid"] == pid and x["vis"] and ("元器件" in x["title"] or "Select a Component" in x["title"])]
        # 也可能弹出新的数据库报错
        for d in dialogs_of(pid):
            h = d["hwnd"]
            if h in seen_dlg:
                continue
            txt = dialog_text(h)
            shot = os.path.join(outdir, "shots", "dlg_after_ctrlw.png")
            try:
                G.screenshot(h, shot)
            except Exception:
                shot = None
            seen_dlg[h] = {"title": d["title"], "text": txt, "shot": shot,
                           "at": round(time.time() - T0, 2)}
            ev("dialog_after_ctrlw", title=d["title"], text=txt, shot=shot)

        if cands:
            hw = cands[0]["hwnd"]
            r = G.rect(hw)
            shot = os.path.join(outdir, "shots", "select_component.png")
            try:
                G.screenshot(hw, shot)
            except Exception:
                shot = None
            kids = dump_children(hw)
            classes = {}
            for k in kids:
                classes[k["cls"]] = classes.get(k["cls"], 0) + 1
            lib_result = {
                "opened": True,
                "title": cands[0]["title"],
                "size": [r[2] - r[0], r[3] - r[1]],
                "child_classes": classes,
                "n_child_texts": len([k for k in kids if k["text"].strip()]),
                "sample_texts": [k["text"] for k in kids if k["text"].strip()][:25],
                "shot": shot,
            }
            ev("component_browser", **{k: v for k, v in lib_result.items() if k != "shot"})
        else:
            lib_result = {"opened": False,
                          "reason": "Ctrl+W 后没有出现'选择一个元器件'窗口"}
            ev("component_browser", opened=False)

    # ---- 收尾 ----
    print("[5] 收尾 …")
    full = os.path.join(outdir, "shots", "final_screen.png")
    try:
        G.screenshot_screen(full)
    except Exception:
        full = None
    snap["ldb_after"] = ldb_files()
    snap["db_files_after"] = db_files()
    snap["dialogs"] = seen_dialogs_text
    snap["db_errors"] = [d for d in seen_dialogs_text if d.get("is_db_error")]
    snap["main_window_seen"] = bool(main_win)
    snap["process_dead_at"] = proc_dead_at
    snap["component_browser"] = lib_result
    snap["final_screen"] = full
    snap["crashed"] = proc_dead_at is not None
    snap["verdict"] = ("DB_FAIL" if snap["db_errors"]
                       else "DB_OK" if main_win else "NO_UI")

    for p in G.multisim_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)

    with open(os.path.join(outdir, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    tl.close()
    write_report(outdir, snap, seen_dlg)
    print("\n[6] 产物目录: %s" % outdir)
    return 0


def write_report(outdir, snap, dialogs):
    L = []
    L.append("# Multisim 数据库诊断 — %s (%s)\n" % (snap["ts"], snap["mode"]))
    L.append("## 结论速览\n")
    L.append("**判定: `%s`**\n" % snap.get("verdict"))
    if snap.get("db_errors"):
        L.append("**出现了数据库报错弹窗：**\n")
        for d in snap["db_errors"]:
            L.append("- 标题: `%s`" % d["title"])
            for t in d["text"]:
                L.append("  - `%s`" % t)
    else:
        L.append("**没有出现数据库报错弹窗。**（闪屏不算）")
    L.append("")
    if snap.get("component_browser"):
        cb = snap["component_browser"]
        if cb.get("opened"):
            L.append("- 元件选择窗口：**打开了**，标题 `%s`，尺寸 %s，有文字的控件 %d 个"
                     % (cb["title"], cb["size"], cb["n_child_texts"]))
            L.append("- 控件类别: `%s`" % json.dumps(cb["child_classes"], ensure_ascii=False))
            L.append("- 可见文本样本: `%s`" % json.dumps(cb["sample_texts"], ensure_ascii=False)[:800])
        else:
            L.append("- 元件选择窗口：**没打开** —— %s" % cb.get("reason"))
    L.append("- 进程在 %s 秒时消失（%s）"
             % (snap.get("process_dead_at"), "崩溃/退出" if snap["crashed"] else "仍存活"))
    L.append("")

    L.append("## 环境\n")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    for k in ("mode", "python", "bits", "windows", "os_build", "locale_LCID",
              "multisim_exe", "multisim_file_version", "pid"):
        L.append("| %s | `%s` |" % (k, snap.get(k)))
    L.append("| launch | `%s` |" % json.dumps(snap.get("launch"), ensure_ascii=False))
    L.append("")

    L.append("## 数据库文件（启动前）\n")
    L.append("| 目录 | 文件 | 字节 | 修改时间 | sha1(前1MB) |")
    L.append("|---|---|---|---|---|")
    for f in snap["db_files"]:
        if not f.get("exists", True):
            L.append("| `%s` | *(目录不存在)* | | | |" % f["dir"])
        else:
            L.append("| `%s` | `%s` | %s | %s | `%s` |"
                     % (f["dir"], f["name"], f["bytes"], f["mtime"], f["sha1_head"]))
    L.append("")

    L.append("## .ldb 锁文件\n")
    L.append("- 启动前: `%s`" % json.dumps(snap.get("ldb_before"), ensure_ascii=False))
    L.append("- 启动后: `%s`" % json.dumps(snap.get("ldb_after"), ensure_ascii=False))
    L.append("")

    L.append("## Jet 4.0 注册表\n")
    L.append("```json")
    L.append(json.dumps(snap.get("jet_registry"), ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")

    L.append("## 弹窗原文\n")
    if not dialogs:
        L.append("*(无)*")
    for h, d in dialogs.items():
        L.append("### `%s`  @%ss\n" % (d["title"], d["at"]))
        for t in d["text"]:
            L.append("- `%s`" % t)
        if d.get("shot"):
            L.append("\n![shot](%s)\n" % os.path.relpath(d["shot"], outdir))
        L.append("")

    with open(os.path.join(outdir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run")
    ap.add_argument("--mode", choices=("direct", "com"), default="direct",
                    help="direct=双击等价; com=v0.8 的 Dispatch+Connect")
    ap.add_argument("--wait", type=int, default=25, help="盯窗口秒数")
    ap.add_argument("--ctrlw", action="store_true", help="按 Ctrl+W 实测元件库")
    ap.add_argument("--ctrlw-wait", type=float, default=4.0)
    ap.add_argument("--auto-ok", action="store_true", help="抓到弹窗自动点确定，看连环弹窗")
    ap.add_argument("--max-ok", type=int, default=5)
    ap.add_argument("--clean-ldb", action="store_true", help="启动前清理 .ldb 锁文件")
    a = ap.parse_args()
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
