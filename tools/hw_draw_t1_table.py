# -*- coding: utf-8 -*-
"""任务一 · 表 1 用的 uo 波形图（紧凑版）。

表 1 三列并排，每格实际宽度只有 4~5 cm，所以按"插入后约 180 px 宽"来设计：
画布 540x360、字号 26~30，缩到 180 px 后仍有 7 pt 左右，打印可读。
只画 uo（表 1 那一行的标题就是「uo波形」），正负峰各一条游标。
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

W, H = 540, 360
BG = (255, 255, 255)
GRID = (232, 236, 242)
AXIS = (110, 116, 126)
TXT = (30, 36, 46)
C_UO = (26, 82, 180)
C_CUR = (196, 42, 42)


def F(p, s):
    return ImageFont.truetype(p, s)


def load_period(pct, guard=8):
    with open(os.path.join(OUT, "wave_p%d.csv" % pct), "r", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        rows = [[float(x) for x in r] for r in rd if r and len(r) == 6]
    rows = rows[:-guard] if guard else rows
    t1 = rows[-1][0]
    sel = [r for r in rows if r[0] >= t1 - 1.0 / 1000.0]
    t0 = sel[0][0]
    return [(r[0] - t0, r[5]) for r in sel]


def render(pct):
    rows = load_period(pct)
    ts = [r[0] for r in rows]
    uo = [r[1] for r in rows]
    vmax, vmin = max(uo), min(uo)
    peak = max(abs(vmax), abs(vmin))

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((12, 6), "RW = %d%%" % pct, font=F(FONT_CN, 27), fill=TXT)
    d.text((W - 12, 10), "峰值 %.3f V" % peak, font=F(FONT_CN, 24),
           fill=C_CUR, anchor="ra")

    x0, y0, x1, y1 = 70, 58, W - 14, 298
    tmax = ts[-1] or 1e-3
    pad = (vmax - vmin) * 0.16
    lo = min(vmin - pad, 0.0)
    hi = max(vmax + pad, 0.0)

    nt = 4
    for i in range(nt + 1):
        y = y0 + (y1 - y0) * i / nt
        d.line([(x0, y), (x1, y)], fill=GRID, width=1)
    for i in range(5):
        x = x0 + (x1 - x0) * i / 4
        d.line([(x, y0), (x, y1)], fill=GRID, width=1)

    def X(t):
        return x0 + (x1 - x0) * (t / tmax)

    def Y(v):
        return y1 - (y1 - y0) * (v - lo) / (hi - lo)

    if lo < 0 < hi:
        d.line([(x0, Y(0)), (x1, Y(0))], fill=AXIS, width=1)
    d.line([(X(t), Y(v)) for t, v in zip(ts, uo)], fill=C_UO, width=4,
           joint="curve")
    d.rectangle([x0, y0, x1, y1], outline=AXIS, width=1)

    # 纵轴刻度
    fs = F(FONT_EN, 19)
    for i in range(nt + 1):
        v = hi - (hi - lo) * i / nt
        d.text((x0 - 7, y0 + (y1 - y0) * i / nt), "%.2f" % v, font=fs,
               fill=AXIS, anchor="rm")
    d.text((x0 + 8, y0 + 5), "uo / V", font=F(FONT_CN, 20), fill=C_UO)

    # 游标
    for v in (vmax, vmin):
        if abs(v) < 1e-9:
            continue
        yv = Y(v)
        d.line([(x0, yv), (x1, yv)], fill=C_CUR, width=1)
        d.text((x1 - 5, yv - 4), "%.3f" % v, font=F(FONT_CN, 18), fill=C_CUR,
               anchor="rd")

    # 时间轴
    ft = F(FONT_EN, 18)
    for i in range(4):
        d.text((x0 + (x1 - x0) * i / 4, y1 + 7), "%.2f" % (i * 0.25),
               font=ft, fill=AXIS, anchor="ma")
    d.text((x1, y1 + 7), "1.00 ms", font=F(FONT_CN, 18), fill=AXIS, anchor="ra")

    p = os.path.join(IMG, "t1_uo_%d.png" % pct)
    img.save(p)
    return p, peak


if __name__ == "__main__":
    with open(os.path.join(OUT, "task1_steady.json"), "r", encoding="utf-8") as f:
        st = {r["pct"]: r for r in json.load(f)}
    for pct in (10, 20, 100):
        p, peak = render(pct)
        print("RW=%3d%%  %s  峰值=%.3f V" % (pct, p, peak))
