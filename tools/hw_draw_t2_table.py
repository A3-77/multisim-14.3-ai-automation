# -*- coding: utf-8 -*-
"""任务二 · 表 2 用的三张波形图（紧凑版，和表 1 同一套配色/字号）。

表 2 只有一行三格，每格插入后约 180 px 宽，所以画布 540x360、字号 22~27。

三格分别对应作业的三小问：
    1) uim=5V  1kHz  —— 示波器 A/B 双踪：ui 与 uo，看限幅后的方波
    2) uim=1V  1kHz  —— 输入够不着阈值（±2.6V），uo 不翻转，卡在负饱和
    3) uim=5V 100Hz  —— 示波器显示方式 B/A，即 uo-ui 的李萨如图（滞回环）
"""
import csv
import math
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
C_UI = (130, 140, 154)
C_UO = (26, 82, 180)
C_CUR = (196, 42, 42)

# 绘图区（左右都留出刻度/单位的位置）
X0, Y0, X1, Y1 = 68, 76, W - 44, 302


def F(p, s):
    return ImageFont.truetype(p, s)


def load(tag, guard=8):
    with open(os.path.join(OUT, "wave_%s.csv" % tag), "r", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        rows = [[float(x) for x in r] for r in rd if r and len(r) == 3]
    rows = rows[:-guard] if guard else rows
    return rows


def window(rows, t_end):
    """取最后 t_end 秒（稳态），时间平移到 0。"""
    t1 = rows[-1][0]
    sel = [r for r in rows if r[0] >= t1 - t_end]
    t0 = sel[0][0]
    return [(r[0] - t0, r[1], r[2]) for r in sel]


def nice_range(vmin, vmax):
    """把纵轴取成整步长的整数倍，避免出现 6.27 / 3.13 这种刻度。"""
    span = max(vmax - vmin, 1e-9)
    step = 1.0 if span <= 4 else 2.0 if span <= 12 else 5.0
    lo = math.floor(vmin / step) * step - step
    hi = math.ceil(vmax / step) * step + step
    n = int(round((hi - lo) / step))
    while n > 8:                       # 刻度太密就加倍步长
        step *= 2
        lo = math.floor(vmin / step) * step - step
        hi = math.ceil(vmax / step) * step + step
        n = int(round((hi - lo) / step))
    return lo, hi, n


def header(d, title, note):
    """标题一行、结论一行（红字），图例靠右上 —— 三样东西互不压。"""
    d.text((12, 4), title, font=F(FONT_CN, 26), fill=TXT)
    d.text((12, 40), note, font=F(FONT_CN, 21), fill=C_CUR)


def legend(d, x, y, items):
    for name, col in items:
        d.line([(x, y + 8), (x + 26, y + 8)], fill=col, width=4)
        d.text((x + 32, y), name, font=F(FONT_CN, 21), fill=TXT)
        x += 32 + 16 * len(name)


def frame(d, lo, hi, n, xlab):
    """画网格 + 边框 + 纵轴刻度 + 纵轴单位。"""
    for i in range(n + 1):
        y = Y0 + (Y1 - Y0) * i / n
        d.line([(X0, y), (X1, y)], fill=GRID, width=1)
    for i in range(4):
        x = X0 + (X1 - X0) * i / 4
        d.line([(x, Y0), (x, Y1)], fill=GRID, width=1)
    if lo < 0 < hi:
        yy = Y1 - (Y1 - Y0) * (0 - lo) / (hi - lo)
        d.line([(X0, yy), (X1, yy)], fill=AXIS, width=1)
    d.rectangle([X0, Y0, X1, Y1], outline=AXIS, width=1)

    fs = F(FONT_EN, 18)
    for i in range(n + 1):
        v = hi - (hi - lo) * i / n
        d.text((X0 - 7, Y0 + (Y1 - Y0) * i / n), "%g" % round(v, 2),
               font=fs, fill=AXIS, anchor="rm")
    if xlab:
        d.text((X0 - 7, Y0 - 7), xlab, font=F(FONT_CN, 18), fill=AXIS,
               anchor="rb")


def x_ticks(d, lo, hi, fmt, unit, ticks=4):
    ft = F(FONT_EN, 18)
    for i in range(ticks + 1):
        x = X0 + (X1 - X0) * i / ticks
        v = lo + (hi - lo) * i / ticks
        d.text((x, Y1 + 7), fmt % v, font=ft, fill=AXIS, anchor="ma")
    d.text((X1 + 8, Y1 + 7), unit, font=F(FONT_CN, 18), fill=AXIS, anchor="la")


def render_trace(tag, t_end, title, note, fname, refs=()):
    rows = window(load(tag), t_end)
    ts = [r[0] for r in rows]
    ui = [r[1] for r in rows]
    uo = [r[2] for r in rows]
    lo, hi, n = nice_range(min(min(ui), min(uo)), max(max(ui), max(uo)))

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, title, note)
    legend(d, 374, 8, [("ui", C_UI), ("uo", C_UO)])
    frame(d, lo, hi, n, "")

    tmax = ts[-1] or 1e-3

    def X(t):
        return X0 + (X1 - X0) * (t / tmax)

    def Y(v):
        return Y1 - (Y1 - Y0) * (v - lo) / (hi - lo)

    d.line([(X(t), Y(v)) for t, v in zip(ts, ui)], fill=C_UI, width=2,
           joint="curve")
    d.line([(X(t), Y(v)) for t, v in zip(ts, uo)], fill=C_UO, width=4,
           joint="curve")

    for v in refs or (max(uo), min(uo)):
        d.line([(X0, Y(v)), (X1, Y(v))], fill=C_CUR, width=1)
        d.text((X1 - 5, Y(v) - 3), "%+.2f" % v, font=F(FONT_CN, 17),
               fill=C_CUR, anchor="rd")

    x_ticks(d, 0.0, tmax * 1000.0, "%g", "ms")
    p = os.path.join(IMG, fname)
    img.save(p)
    return p


def render_xy(tag, title, note, fname):
    """B/A 显示：X = ui，Y = uo，得到滞回环。"""
    rows = window(load(tag), 1.0 / 100.0)      # 一个完整周期
    ui = [r[1] for r in rows]
    uo = [r[2] for r in rows]

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, title, note)

    lo, hi, n = -6.0, 6.0, 4
    frame(d, lo, hi, n, "")

    def X(v):
        return X0 + (X1 - X0) * (v - lo) / (hi - lo)

    def Y(v):
        return Y1 - (Y1 - Y0) * (v - lo) / (hi - lo)

    d.line([(X(v), Y(w)) for v, w in zip(ui, uo)], fill=C_UO, width=3,
           joint="curve")

    th = [ui[i] for i in range(1, len(uo))
          if (uo[i - 1]) * (uo[i]) < 0]
    for v in th:
        d.line([(X(v), Y0), (X(v), Y1)], fill=C_CUR, width=1)
    if th:
        d.text((X(min(th)) - 5, Y1 - 5), "%.2f V" % min(th),
               font=F(FONT_CN, 18), fill=C_CUR, anchor="rd")
        d.text((X(max(th)) + 5, Y1 - 5), "+%.2f V" % max(th),
               font=F(FONT_CN, 18), fill=C_CUR, anchor="ld")

    x_ticks(d, lo, hi, "%g", "")
    d.text((X1 - 8, Y0 + 6), "uo /V", font=F(FONT_CN, 19), fill=C_UO,
           anchor="ra")
    d.text((X1, Y1 + 26), "ui /V", font=F(FONT_CN, 19), fill=C_UO,
           anchor="ra")
    p = os.path.join(IMG, fname)
    img.save(p)
    return p


if __name__ == "__main__":
    print(render_trace("c1_5v_1k", 2.0 / 1000.0,
                       "uim=5V  f=1kHz", "uo=±5.2V", "t2_1.png"))
    print(render_trace("c2_1v_1k", 2.0 / 1000.0,
                       "uim=1V  f=1kHz", "uo=-5.2V 不翻转", "t2_2.png"))
    print(render_xy("c3_5v_100", "uim=5V  f=100Hz", "B/A", "t2_3.png"))
