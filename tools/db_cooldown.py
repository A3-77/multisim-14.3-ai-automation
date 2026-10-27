# -*- coding: utf-8 -*-
"""验证"正常关闭后立刻重开会报数据库错，等一会儿又好了"这个规律。

和 db_cycle.py 的区别
---------------------
db_cycle 用 `taskkill /F` 强杀，句柄是被操作系统硬收回的；
这个工具用 **正常关闭**（发 WM_CLOSE，等价于点右上角 ×），
所以能看到"进程退出后资源还没释放"这类时间相关的问题。

每一轮做这些事
--------------
1. 反复启动，直到拿到一次 **DB_OK**（成功基线）
2. **正常关闭**，记下关闭时刻
3. 关闭后每隔 2 秒探测：主库文件还能不能独占打开 / .ldb 还在不在
4. 等 `gap` 秒，再启动一次，记录 DB_OK / DB_FAIL
5. 再正常关闭

用法
----
    python tools/db_cooldown.py --gaps 0,30,90 --cycles 2
"""
import argparse
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import guiauto as G                                        # noqa: E402
from db_diag import (EXE, DBDIR_PROGRAMDATA,               # noqa: E402
                     dialog_text, dialogs_of, is_db_error,
                     main_window, ldb_files, dump_children)

WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
BM_CLICK = 0x00F5
PRD = os.path.join(DBDIR_PROGRAMDATA, "MSCOMP_S.PRD")


# ---------------------------------------------------------------------------
def kill_all():
    for p in G.multisim_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
    time.sleep(1.2)


def clean_ldb():
    for f in ldb_files():
        try:
            os.remove(f)
        except OSError:
            pass


def prd_locked():
    """主库能不能被独占打开？返回 (能否独占, 错误简述)。"""
    try:
        f = open(PRD, "rb")
        f.close()
        # 用 Win32 更严格的共享模式再试一次
        import win32file
        h = win32file.CreateFile(PRD, win32file.GENERIC_READ, 0, None,
                                 win32file.OPEN_EXISTING, 0, None)
        win32file.CloseHandle(h)
        return True, ""
    except Exception as e:
        return False, str(e)[:120]


def launch_and_probe(wait):
    """启动一次，返回 dict(verdict, dialogs, dead, main_seen)。"""
    t0 = time.time()
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    pid = -1
    while time.time() - t0 < 20:
        pids = sorted(G.multisim_pids())
        if pids:
            pid = pids[-1]
            break
        time.sleep(0.1)

    seen, dbs, win, dead = set(), [], None, False
    while time.time() - t0 < wait:
        if pid not in G.multisim_pids():
            dead = True
            break
        for d in dialogs_of(pid):
            if d["hwnd"] in seen:
                continue
            seen.add(d["hwnd"])
            txt = dialog_text(d["hwnd"])
            if is_db_error(d["title"], txt):
                dbs.extend(txt)
        if win is None:
            win = main_window(pid)
        time.sleep(0.2)

    return {"verdict": "DB_FAIL" if dbs else ("DB_OK" if win else "NO_UI"),
            "dialogs": dbs, "dead": dead, "pid": pid}


def close_graceful(timeout=20):
    """发 WM_CLOSE，处理"是否保存"弹窗，等进程退出。返回 (是否退出, 耗时)。"""
    t0 = time.time()
    pids = sorted(G.multisim_pids())
    if not pids:
        return True, 0.0
    win = None
    for p in pids:
        win = main_window(p)
        if win:
            break
    if not win:
        kill_all()
        return False, round(time.time() - t0, 2)

    G.foreground(win["hwnd"])
    time.sleep(0.3)
    ctypes.windll.user32.PostMessageW(win["hwnd"], WM_CLOSE, 0, 0)

    while time.time() - t0 < timeout:
        time.sleep(0.3)
        # 有"是否保存"之类的弹窗就点"否"
        for p in pids:
            for d in dialogs_of(p):
                for it in dump_children(d["hwnd"]):
                    if it["cls"] == "Button" and it["text"].strip() in ("否(&N)", "否", "No", "&No"):
                        ctypes.windll.user32.SendMessageW(
                            ctypes.windll.user32.GetDlgItem(d["hwnd"], it["id"]), BM_CLICK, 0, 0)
                        break
        if not G.multisim_pids():
            return True, round(time.time() - t0, 2)

    kill_all()
    return False, round(time.time() - t0, 2)


def watch_after_close(seconds=40, step=2.0):
    """关闭后盯着主库能不能独占打开、.ldb 还在不在。"""
    t0 = time.time()
    rows = []
    while time.time() - t0 <= seconds:
        ok, err = prd_locked()
        rows.append({"t": round(time.time() - t0, 1),
                     "prd_free": ok,
                     "ldb": [os.path.basename(x) for x in ldb_files()],
                     "err": err})
        if ok and not ldb_files() and len(rows) > 1:
            break
        time.sleep(step)
    return rows


def open_until_ok(max_try=6, wait=12):
    """反复开，直到拿到 DB_OK。"""
    for i in range(1, max_try + 1):
        r = launch_and_probe(wait)
        print("    基线第 %d 次: %s" % (i, r["verdict"]))
        if r["verdict"] == "DB_OK":
            return True, i
        kill_all()
    return False, max_try


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps", default="0,30,90", help="关闭后等待的秒数，逗号分隔")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--wait", type=int, default=12)
    a = ap.parse_args()
    gaps = [float(x) for x in a.gaps.split(",")]

    results = []
    for gap in gaps:
        for c in range(1, a.cycles + 1):
            print("\n" + "=" * 62)
            print(">>> gap=%gs  第 %d/%d 轮" % (gap, c, a.cycles))
            print("=" * 62)

            kill_all()
            clean_ldb()

            print("  [1] 先拿一次成功基线 …")
            got, tries = open_until_ok(wait=a.wait)
            if not got:
                print("  !! %d 次都没开成功，跳过本轮" % tries)
                results.append({"gap": gap, "cycle": c, "baseline": False})
                kill_all()
                continue
            print("  [2] 基线成功，正常关闭 …")
            closed, cost = close_graceful()
            print("     关闭: %s，耗时 %.1fs" % ("正常退出" if closed else "超时强杀", cost))

            print("  [3] 关闭后监控主库占用 / .ldb …")
            rows = watch_after_close(seconds=min(max(gap, 12), 40))
            first_free = next((r["t"] for r in rows if r["prd_free"]), None)
            print("     主库最早可独占: %s" % ("%.1fs" % first_free if first_free is not None else ">40s 仍被占用"))
            for r in rows[:4]:
                print("       t=%4.1fs  可独占=%-5s  .ldb=%s" % (r["t"], r["prd_free"], r["ldb"] or "无"))

            if gap > 0:
                left = gap - rows[-1]["t"] if rows else gap
                if left > 0:
                    print("  [4] 再等 %.0fs …" % left)
                    time.sleep(left)
            else:
                print("  [4] gap=0，立刻重开")

            print("  [5] 重开 …")
            r = launch_and_probe(a.wait)
            print("     -> %s%s" % (r["verdict"], ("  弹窗: " + " / ".join(r["dialogs"])) if r["dialogs"] else ""))
            results.append({"gap": gap, "cycle": c, "baseline": True,
                            "verdict": r["verdict"], "closed_gracefully": closed,
                            "close_s": cost, "prd_free_at": first_free})

            close_graceful()
            kill_all()
            clean_ldb()

    print("\n\n" + "=" * 62)
    print("汇总：正常关闭后，等不同时间再打开")
    print("=" * 62)
    print("%-8s %-6s %-10s %-12s" % ("等待", "轮次", "重开结果", "主库可独占(s)"))
    print("-" * 46)
    for r in results:
        if not r.get("baseline"):
            print("%-8s %-6s %-10s %-12s" % ("%gs" % r["gap"], r["cycle"], "基线失败", "-"))
        else:
            print("%-8s %-6s %-10s %-12s" % ("%gs" % r["gap"], r["cycle"], r["verdict"],
                                             r.get("prd_free_at")))
    kill_all()
    clean_ldb()
    return 0


if __name__ == "__main__":
    sys.exit(main())
