# -*- coding: utf-8 -*-
"""把任务一的仿真波形画成示波器风格的 PNG，供插进作业表 1。

每张图：上panel = uo（1 个周期），下panel = ui（参考）。
两条游标分别标出 uo 的正峰 / 负峰，标题给出峰值（= max|uo|）。
"""
import csv
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "hw1")
IMG = os.path.join(OUT, "img")
os.makedirs(IMG, exist_ok=True)

FONT_CN = "C:/Windows/Fonts/msyh.ttc"
FONT_EN = "C:/Windows/Fonts/arial.ttf"

W, H = 840, 520
BG = (255, 255, 255)
GRID = (228, 232, 238)
AXIS = (96, 102, 112)
TXT = (34, 40, 50)
C_UO = (28, 86, 186)
C_UI = (200, 104, 16)
C_CUR = (198, 44, 44)
C_DIM = (120, 126, 136)


def F(path, size):
    return ImageFont.truetype(path, size)


def load_period(pct, guard=8):
    p = os.path.join(OUT, "wave_p%d.csv" % pct)
    with open(p, "r", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        rows = [[float(x) for x in r] for r in rd if r and len(r) == 6]
    rows = rows[:-guard] if guard else rows
    t1 = rows[-1][0]
    sel = [r for r in rows if r[0] >= t1 - 1.0 / 1000.0]
    t0 = sel[0][0]
    return [(r[0] - t0, r[1], r[5]) for r in sel]


def panel(d, box, ts, vs, color, name, unit, nticks=5, zero=True):
    x0, y0, x1, y1 = box
    tmax = ts[-1] or 1e-3
    vmin, vmax = min(vs), max(vs)
    if vmax - vmin < 1e-12:
        vmax = vmin + 1e-3
    pad = (vmax - vmin) * 0.18
    lo, hi = vmin - pad, vmax + pad
    if zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)

    for i in range(nticks + 1):
        y = y0 + (y1 - y0) * i / nticks
        d.line([(x0, y), (x1, y)], fill=GRID, width=1)
    for i in range(9):
        x = x0 + (x1 - x0) * i / 8
        d.line([(x, y0), (x, y1)], fill=GRID, width=1)

    def X(t):
        return x0 + (x1 - x0) * (t / tmax)

    def Y(v):
        return y1 - (y1 - y0) * (v - lo) / (hi - lo)

    if lo < 0 < hi:
        d.line([(x0, Y(0)), (x1, Y(0))], fill=AXIS, width=1)

    d.line([(X(t), Y(v)) for t, v in zip(ts, vs)], fill=color, width=3,
           joint="curve")
    d.rectangle([x0, y0, x1, y1], outline=AXIS, width=1)

    d.text((x0 + 10, y0 + 6), "%s / %s" % (name, unit), font=F(FONT_CN, 19),
           fill=color)
    fs = F(FONT_EN, 15)
    for i in range(nticks + 1):
        v = hi - (hi - lo) * i / nticks
        y = y0 + (y1 - y0) * i / nticks
        s = ("%.2f" % v) if unit == "V" else ("%.0f" % (v * 1e3))
        d.text((x0 - 8, y), s, font=fs, fill=AXIS, anchor="rm")
    return X, Y


def render(pct, uce):
    rows = load_period(pct)
    ts = [r[0] for r in rows]
    ui = [r[1] for r in rows]
    uo = [r[2] for r in rows]

    vmax, vmin = max(uo), min(uo)
    peak = max(abs(vmax), abs(vmin))
    ppp = vmax - vmin

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((24, 14), "RW = %d%%" % pct, font=F(FONT_CN, 24), fill=TXT)
    d.text((W - 24, 18), "uo 峰值 = %.3f V" % peak, font=F(FONT_CN, 21),
           fill=C_CUR, anchor="ra")

    b_uo = (92, 62, W - 26, 306)
    X, Y = panel(d, b_uo, ts, uo, C_UO, "uo", "V", 5)

    # 正峰 / 负峰 两条游标
    for v, tag in ((vmax, "+"), (vmin, "-")):
        if abs(v) < 1e-6:
            continue
        yv = Y(v)
        d.line([(b_uo[0], yv), (b_uo[2], yv)], fill=C_CUR, width=1)
        d.text((b_uo[2] - 6, yv - 7), "%.3f V" % v, font=F(FONT_CN, 17),
               fill=C_CUR, anchor="ra")

    b_ui = (92, 356, W - 26, 452)
    panel(d, b_ui, ts, ui, C_UI, "ui", "mV", 2)

    f = F(FONT_EN, 15)
    for i in range(4):
        x = b_ui[0] + (b_ui[2] - b_ui[0]) * i / 4
        d.text((x, b_ui[3] + 7), "%.2f" % (i * 0.25), font=f, fill=AXIS,
               anchor="ma")
    # 末端刻度顺带当单位标签，避免和 "t / ms" 挤在一起
    d.text((b_ui[2], b_ui[3] + 7), "1.00 ms", font=F(FONT_CN, 15), fill=AXIS,
           anchor="ra")

    d.text((24, H - 30),
           "UCE = %.2f V      峰峰值 uo(pp) = %.3f V" % (uce, ppp),
           font=F(FONT_CN, 17), fill=C_DIM)

    p = os.path.join(IMG, "task1_uo_p%d.png" % pct)
    img.save(p)
    return p, peak, ppp


if __name__ == "__main__":
    with open(os.path.join(OUT, "task1_steady.json"), "r", encoding="utf-8") as f:
        st = {r["pct"]: r for r in json.load(f)}
    for pct in (10, 20, 100):
        p, peak, ppp = render(pct, st[pct]["UCE"])
        print("RW=%3d%%  -> %s   峰值=%.3f V  峰峰=%.3f V"
              % (pct, p, peak, ppp))
