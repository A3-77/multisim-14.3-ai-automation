# -*- coding: utf-8 -*-
"""从真实 CSV 画波形图（发布素材）。

数据来源：out/mcp/sessions/c-eccf480d70/sims/s-042f992be7.csv
          —— 那次 MCP simulate 从 Multisim COM 读回来的原始采样点
不重采样、不插值、不美化，只做坐标映射。
"""
import csv
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                   "sims", "s-042f992be7.csv")
OUT = os.path.join(ROOT, "docs", "case", "agent_rc_500hz_waveform.png")

FONT = "C:/Windows/Fonts/msyh.ttc"
FONTB = "C:/Windows/Fonts/msyhbd.ttc"

W, H = 1280, 820
BG = "#ffffff"
INK = "#1f2d3d"
MUTED = "#6b7c8f"
GRID = "#e6ecf2"
AXIS = "#b8c4d0"
C_IN = "#5b7c99"
C_OUT = "#d94f30"


def f(sz, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, sz)


def load():
    with open(CSV, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    names = rows[0][1:]
    t, ch = [], {n: [] for n in names}
    for r in rows[1:]:
        if not r:
            continue
        t.append(float(r[0]) * 1000.0)          # -> ms
        for i, n in enumerate(names, 1):
            ch[n].append(float(r[i]))
    return names, t, ch


def panel(d, x0, y0, w, h, t, series, ylim, tlim, title, sub=None,
          yticks=5, xticks=6):
    """画一个坐标面板。series = [(label, ys, color)]"""
    left, right = x0 + 74, x0 + w
    top, bottom = y0 + 34, y0 + h - 34

    d.rectangle([left, top, right, bottom], fill="#fbfdfe", outline=GRID)
    # 网格 + 刻度
    for i in range(yticks + 1):
        yy = top + (bottom - top) * i / yticks
        v = ylim[0] + (ylim[1] - ylim[0]) * (1 - i / yticks)
        d.line([left, yy, right, yy], fill=GRID)
        d.text((left - 10, yy), "%+.2f" % v, font=f(13), fill=MUTED, anchor="rm")
    for i in range(xticks + 1):
        xx = left + (right - left) * i / xticks
        v = tlim[0] + (tlim[1] - tlim[0]) * i / xticks
        d.line([xx, top, xx, bottom], fill=GRID)
        d.text((xx, bottom + 8), "%.2f" % v, font=f(13), fill=MUTED, anchor="ma")

    # 0 V 线
    def ymap(v):
        return bottom - (v - ylim[0]) / (ylim[1] - ylim[0]) * (bottom - top)
    if ylim[0] < 0 < ylim[1]:
        d.line([left, ymap(0), right, ymap(0)], fill=AXIS, width=1)

    # 曲线
    idx = [i for i, x in enumerate(t) if tlim[0] <= x <= tlim[1]]
    for label, ys, color in series:
        pts = [(left + (t[i] - tlim[0]) / (tlim[1] - tlim[0]) * (right - left),
                ymap(ys[i])) for i in idx]
        if len(pts) > 1:
            d.line(pts, fill=color, width=2, joint="curve")

    # 标题
    d.text((left, y0 + 4), title, font=f(17, True), fill=INK)
    if sub:
        d.text((right, y0 + 7), sub, font=f(13), fill=MUTED, anchor="ra")
    d.text(((left + right) / 2, bottom + 26), "时间 (ms)", font=f(13),
           fill=MUTED, anchor="ma")
    return left, top, right, bottom


def main():
    names, t, ch = load()
    v_in, v_out = ch[names[0]], ch[names[1]]
    print("样本 %d 点，t=[%.4f, %.4f] ms" % (len(t), t[0], t[-1]))

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # ---- 标题区 ----
    d.text((48, 34), "Agent Acceptance Test · 一阶 RC 低通", font=f(28, True), fill=INK)
    d.text((48, 76),
           "1 V / 1 kHz 正弦输入  ·  R = 10 kΩ  ·  C = 33 nF  ·  fc = 482.3 Hz",
           font=f(16), fill=MUTED)
    d.text((48, 102),
           "数据来源：MCP simulate → Multisim 14.3 → COM 读回的原始采样点（1200 点 / 6 ms / 200 kHz）",
           font=f(14), fill=MUTED)

    # ---- 图例 ----
    lx = 48
    for label, color in (("Vin（输入）", C_IN), ("Vout（输出）", C_OUT)):
        d.line([lx, 140, lx + 34, 140], fill=color, width=3)
        d.text((lx + 42, 140), label, font=f(15), fill=INK, anchor="lm")
        lx += 42 + int(d.textlength(label, font=f(15))) + 34

    # ---- 上：全窗口 ----
    panel(d, 40, 168, W - 80, 300, t, [("in", v_in, C_IN), ("out", v_out, C_OUT)],
          (-1.15, 1.15), (t[0], t[-1]),
          "完整仿真窗口（能看到起始几毫秒的电容充电暂态）",
          "前 40% 不参与拟合")

    # ---- 下：放大两周期 ----
    panel(d, 40, 492, W - 80, 250, t, [("in", v_in, C_IN), ("out", v_out, C_OUT)],
          (-1.15, 1.15), (1.0, 3.0),
          "放大：1–3 ms（两个周期）—— 输出滞后约 64°",
          "Vout 明显滞后且幅值约为 Vin 的 43%")

    # ---- 关键数字 ----
    bx, by = 48, 762
    items = [("输入幅值", "0.996791 V"), ("输出实测", "0.431897 V"),
             ("输出理论", "0.434405 V"), ("误差", "-0.577 %"),
             ("增益", "0.433288"), ("相位", "-64.33°")]
    cx = bx
    for k, v in items:
        d.text((cx, by), k, font=f(13), fill=MUTED)
        d.text((cx, by + 18), v, font=f(17, True), fill=INK)
        cx += 196

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print("-> %s (%d 字节)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
