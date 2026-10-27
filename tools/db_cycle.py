# -*- coding: utf-8 -*-
"""数据库可用性 A/B 循环实验。

每一轮固定做两件事：
    A 组：先删掉所有 .ldb 锁文件 -> 启动 -> 看有没有"主数据库无法访问"
    B 组：不删（上一轮 taskkill 留下的 .ldb 还在）-> 启动 -> 看有没有

用来证明：残留 .ldb 是否就是"时好时坏"的直接原因。

用法:  python tools/db_cycle.py --rounds 3 --wait 12
"""
import argparse
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import guiauto as G          # noqa: E402
from db_diag import (EXE, DBDIR_PROGRAMDATA, DBDIR_APPDATA,  # noqa: E402
                     dialog_text, dialogs_of, is_db_error, main_window, ldb_files)


def kill_all():
    for p in G.multisim_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
    time.sleep(1.2)


def clean_ldb():
    removed = []
    for f in ldb_files():
        try:
            os.remove(f)
            removed.append(os.path.basename(f))
        except OSError:
            pass
    return removed


def one_run(wait):
    """启动一次，返回 (verdict, 弹窗文本, 是否崩溃)。"""
    t0 = time.time()
    subprocess.Popen([EXE], creationflags=0x00000008, close_fds=True)
    pid = -1
    while time.time() - t0 < 20:
        pids = sorted(G.multisim_pids())
        if pids:
            pid = pids[-1]
            break
        time.sleep(0.1)

    seen, db_txt = set(), []
    win = None
    dead = False
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
                db_txt.extend(txt)
        if win is None:
            win = main_window(pid)
        time.sleep(0.2)

    ldb_now = [os.path.basename(x) for x in ldb_files()]
    verdict = "DB_FAIL" if db_txt else ("DB_OK" if win else "NO_UI")
    return verdict, db_txt, dead, ldb_now


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--wait", type=int, default=12)
    a = ap.parse_args()

    rows = []
    for i in range(1, a.rounds + 1):
        # --- A 组：清干净 ---
        kill_all()
        rem = clean_ldb()
        print("\n=== 第 %d 轮 A 组：清理 .ldb %s ===" % (i, rem or "(本来就没有)"))
        v, txt, dead, ldb = one_run(a.wait)
        print("    -> %-8s 崩溃=%s 启动后 .ldb=%s" % (v, dead, ldb or "无"))
        if txt:
            print("       弹窗: %s" % " / ".join(txt))
        rows.append(("A 清理后", v, dead, bool(ldb)))

        # --- B 组：直接再启（上一步 taskkill 已留下 .ldb）---
        kill_all()
        print("=== 第 %d 轮 B 组：保留残留 .ldb %s ===" % (i, [os.path.basename(x) for x in ldb_files()] or "(无)"))
        v, txt, dead, ldb = one_run(a.wait)
        print("    -> %-8s 崩溃=%s 启动后 .ldb=%s" % (v, dead, ldb or "无"))
        if txt:
            print("       弹窗: %s" % " / ".join(txt))
        rows.append(("B 有残留", v, dead, bool(ldb)))

    print("\n\n================ 汇总 ================")
    print("%-12s %-9s %-6s" % ("条件", "结果", "崩溃"))
    print("-" * 34)
    for name, v, dead, _ in rows:
        print("%-12s %-9s %-6s" % (name, v, "是" if dead else "否"))

    a_ok = sum(1 for n, v, _, _ in rows if n.startswith("A") and v == "DB_OK")
    b_fail = sum(1 for n, v, _, _ in rows if n.startswith("B") and v == "DB_FAIL")
    n = a.rounds
    print("\nA 组(清 .ldb) 成功: %d/%d" % (a_ok, n))
    print("B 组(留 .ldb) 报错: %d/%d" % (b_fail, n))
    kill_all()
    clean_ldb()
    print("\n已收尾：杀掉 Multisim 并清掉 .ldb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
