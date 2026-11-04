# -*- coding: utf-8 -*-
"""任务一 · 稳态分析：从 wave_p*.csv 取末段完整周期，算静态工作点与 uo 峰值。

输出的数字才是要填进表 1 的：
    UCE = Vc(稳态均值) - Ve(稳态均值)
    uo 峰值 = 末段一个完整周期的 (max - min)/2

注意：CSV 最后一行是仿真收尾的残行（数据列会整体错位/归零），必须丢掉。
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "hw1")

FREQ = 1000.0
NAMES = ["vi", "vb", "vc", "ve", "vo"]
GUARD = 8          # 丢掉末尾残行


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        rows = [[float(x) for x in r] for r in rd if r and len(r) == 6]
    return rows[:-GUARD] if GUARD else rows


def analyze(pct):
    rows = load(os.path.join(OUT, "wave_p%d.csv" % pct))
    t = [r[0] for r in rows]
    t1 = t[-1]
    period = 1.0 / FREQ

    w0 = t1 - 3 * period                       # 稳态：末 3 个周期
    idx = [i for i, tt in enumerate(t) if tt >= w0]
    p0 = t1 - period                           # 末 1 个完整周期
    pidx = [i for i, tt in enumerate(t) if tt >= p0]

    res = {"pct": pct, "win": [round(w0, 6), round(t1, 6)], "n": len(idx)}
    for k, nm in enumerate(NAMES):
        col = [rows[i][k + 1] for i in idx]
        res[nm] = {"mean": sum(col) / len(col), "min": min(col), "max": max(col)}

    def pp(k):
        col = [rows[i][k + 1] for i in pidx]
        return max(col) - min(col)

    res["ui_pp"] = pp(0)
    res["uo_pp"] = pp(4)
    res["uo_peak"] = res["uo_pp"] / 2.0
    res["ui_peak"] = res["ui_pp"] / 2.0
    res["Av"] = res["uo_pp"] / res["ui_pp"] if res["ui_pp"] > 1e-12 else 0.0
    res["UCE"] = res["vc"]["mean"] - res["ve"]["mean"]
    res["UCE_pp"] = pp(2)                      # 集电极交流摆幅
    return res


if __name__ == "__main__":
    out = []
    for pct in (10, 20, 100):
        r = analyze(pct)
        out.append(r)
        print("=== RW = %d%%" % pct)
        print("   稳态窗口 %.5f~%.5f s（末 3 周期，%d 点）"
              % (r["win"][0], r["win"][1], r["n"]))
        print("   Vb=%.4f  Vc=%.4f  Ve=%.4f  Vo(DC)=%.4f"
              % (r["vb"]["mean"], r["vc"]["mean"],
                 r["ve"]["mean"], r["vo"]["mean"]))
        print("   >>> UCE = %.3f V" % r["UCE"])
        print("   ui_pp=%.5f V   uo_pp=%.4f V   uo峰值=%.4f V   Av=%.2f"
              % (r["ui_pp"], r["uo_pp"], r["uo_peak"], r["Av"]))
        print("   vo min/max = %.4f / %.4f V" % (r["vo"]["min"], r["vo"]["max"]))
        print()

    with open(os.path.join(OUT, "task1_steady.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("-> out/hw1/task1_steady.json")
