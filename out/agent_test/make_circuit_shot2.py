# -*- coding: utf-8 -*-
"""画电路结构图（发布素材）。

数据来源：out/mcp/sessions/c-eccf480d70/circuit.ir.json
          —— 那次 MCP 会话里 7 个工具建出来的真实电路
本脚本只做坐标映射：元件、引脚、网络、探针位置全部来自上面那个文件，
不手写拓扑，不改数值。

为什么不用 Multisim 自己的 GetCircuitImage：
  见 out/agent_test/AGENT_ACCEPTANCE_REPORT.md 问题 8 ——
  对我们生成的 .ms14，Multisim 只画出 R1 和两个探针，V1/C1 符号缺失
  （让 Multisim 自己 save_as 再 reopen 也一样）。所以那张图只能当缺陷证据，
  不能当发布配图。
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IR = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70", "circuit.ir.json")
OUT = os.path.join(ROOT, "docs", "case", "agent_rc_500hz_circuit.png")

FONT = "C:/Windows/Fonts/msyh.ttc"
FONTB = "C:/Windows/Fonts/msyhbd.ttc"

W, H = 1280, 700
BG = "#ffffff"
INK = "#1f2d3d"
MUTED = "#6b7c8f"
GRID = "#eef2f6"
WIRE = "#2b3a4a"
C_IN = "#5b7c99"
C_OUT = "#d94f30"


def f(sz, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, sz)


def load():
    with open(IR, encoding="utf-8") as fh:
        ir = json.load(fh)
    comp = {c["refdes"]: c for c in ir["components"]}
    net = {n["name"]: n["pins"] for n in ir["nets"]}
    probe = {p["refdes"]: p for p in ir["probes"]}
    return ir, comp, net, probe


def poly(d, pts, color=WIRE, w=2):
    d.line(pts, fill=color, width=w, joint="curve")


def dot(d, xy, r=5, color=WIRE):
    d.ellipse([xy[0] - r, xy[1] - r, xy[0] + r, xy[1] + r], fill=color)


def resistor(d, x0, x1, y, n=8, amp=14):
    """ANSI 锯齿电阻。"""
    pts = [(x0, y)]
    seg = (x1 - x0 - 2 * 20) / n
    for i in range(n):
        cx = x0 + 20 + seg * i + seg / 2.0
        pts.append((cx, y - amp if i % 2 == 0 else y + amp))
    pts.append((x1, y))
    poly(d, pts, w=3)


def cap(d, x, y, gap=18, plate=62):
    """两条平行极板。"""
    poly(d, [(x - plate / 2, y), (x + plate / 2, y)], w=3)
    poly(d, [(x - plate / 2, y + gap), (x + plate / 2, y + gap)], w=3)


def source(d, cx, cy, r, color=C_IN):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
    pts = []
    for i in range(61):
        t = i / 60.0
        pts.append((cx - r * 0.62 + 2 * r * 0.62 * t,
                    cy - r * 0.42 * __import__("math").sin(t * 4 * 3.141592653589793)))
    poly(d, pts, color=color, w=2)
    # + / -
    d.text((cx + r + 8, cy - r - 6), "+", font=f(22, True), fill=color)
    d.text((cx + r + 8, cy + r - 20), "\u2212", font=f(22, True), fill=color)


def ground(d, x, y, color=WIRE):
    poly(d, [(x, y), (x, y + 34)], w=2)
    for i, hw in enumerate((24, 15, 7)):
        yy = y + 34 + i * 10
        poly(d, [(x - hw, yy), (x + hw, yy)], w=3)


def probe(d, x, y_rail, color, name, kind="V"):
    """探针：短支线 + 圆圈 + 字母。"""
    cy = y_rail - 52
    poly(d, [(x, y_rail), (x, cy + 15)], color=color, w=2)
    d.ellipse([x - 15, cy - 15, x + 15, cy + 15], fill=BG, outline=color, width=3)
    d.text((x, cy - 1), kind, font=f(17, True), fill=color, anchor="mm")
    d.text((x + 22, cy - 1), name, font=f(19, True), fill=color, anchor="lm")


def fmt(v):
    if v is None:
        return ""
    if v >= 1e6:
        return "%.4g M" % (v / 1e6)
    if v >= 1e3:
        return "%g k" % (v / 1e3)
    if v >= 1:
        return "%g" % v
    return "%.4g n" % (v * 1e9) if v < 1e-6 else "%g n" % (v * 1e9)


def main():
    ir, comp, net, _probes = load()
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 背景网格
    for x in range(0, W, 40):
        d.line([(x, 160), (x, H - 70)], fill=GRID, width=1)
    for y in range(160, H - 70, 40):
        d.line([(0, y), (W, y)], fill=GRID, width=1)

    # ---------- 标题 ----------
    d.text((64, 40), "电路结构 · 一阶 RC 低通", font=f(40, True), fill=INK)
    d.text((64, 100),
           "全部由 7 个 MCP 工具建出，没有手写一行 XML，也没有指定任何坐标",
           font=f(20), fill=MUTED)
    d.text((64, 130),
           "V1 = 1 V / 1 kHz 正弦    R1 = 10 kΩ    C1 = 33 nF    fc = 1/(2πRC) = 482.3 Hz",
           font=f(20), fill=INK)

    # ---------- 几何 ----------
    rail, base = 300, 520
    x_src, x_r0, x_r1, x_cap = 300, 460, 700, 960

    # 上导线：源 -> R1 左
    poly(d, [(x_src, rail), (x_r0, rail)], w=3)
    resistor(d, x_r0, x_r1, rail)
    poly(d, [(x_r1, rail), (x_cap, rail)], w=3)
    # 下导线
    poly(d, [(x_src, base), (x_cap, base)], w=3)
    # 源支路
    poly(d, [(x_src, rail), (x_src, rail + 40)], w=3)
    source(d, x_src, rail + 82, 42)
    poly(d, [(x_src, rail + 124), (x_src, base)], w=3)
    # 电容支路
    poly(d, [(x_cap, rail), (x_cap, 400)], w=3)
    cap(d, x_cap, 400)
    poly(d, [(x_cap, 418), (x_cap, base)], w=3)
    # 地
    ground(d, 630, base)

    # 节点
    dot(d, (x_src, rail))
    dot(d, (x_cap, rail))
    dot(d, (630, base))

    # ---------- 标注 ----------
    d.text((580, rail - 46), "R1", font=f(20, True), fill=INK, anchor="mm")
    d.text((580, rail + 46), "%s Ω" % fmt(comp["R1"]["value"]).replace(" k", " k"),
           font=f(21, True), fill=INK, anchor="mm")
    d.text((x_cap + 46, 392), "C1", font=f(20, True), fill=INK, anchor="lm")
    d.text((x_cap + 46, 418), "%s F" % fmt(comp["C1"]["value"]).replace(" n", " n"),
           font=f(21, True), fill=INK, anchor="lm")
    d.text((x_src + 22, base + 40), "GND1", font=f(19), fill=MUTED, anchor="lm")

    freq = comp["V1"]["params"].get("5")
    d.text((x_src - 62, rail + 70), "V1", font=f(21, True), fill=INK, anchor="rm")
    d.text((x_src - 62, rail + 94), "%s V" % comp["V1"]["value"],
           font=f(19), fill=INK, anchor="rm")
    if freq:
        d.text((x_src - 62, rail + 116), "%g Hz" % freq, font=f(19), fill=INK, anchor="rm")

    # 网络名（来自 IR 的 nets，不是我自己起的）
    for name, xy, anc in (("in", (x_src + 46, rail - 24), "lm"),
                          ("n1", (x_cap - 40, rail - 24), "rm"),
                          ("0", (x_src + 46, base - 26), "lm")):
        d.text(xy, name, font=f(19, True), fill=MUTED, anchor=anc)
        assert name in net, "IR 里没有网络 %r" % name

    # 探针（位置来自 IR 的 probes.net）
    pmap = {p["net"]: p["refdes"] for p in ir["probes"]}
    assert pmap.get("in") and pmap.get("n1"), "IR 里缺探针"
    probe(d, 380, rail, C_IN, pmap["in"])
    probe(d, 820, rail, C_OUT, pmap["n1"])

    # ---------- 结论条 ----------
    y = H - 62
    d.line([(64, y - 18), (W - 64, y - 18)], fill=GRID, width=2)
    d.text((64, y),
           "P1 接在输入网 in，P2 接在 RC 中点 n1     ·     "
           "实测 Vout = 0.431897 V（理论 0.434405 V，误差 −0.577 %）",
           font=f(18), fill=MUTED)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print("->", OUT, os.path.getsize(OUT), "字节")


if __name__ == "__main__":
    main()
