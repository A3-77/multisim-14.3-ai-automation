#!/usr/bin/env python3
"""从仓库里已提交的真实 CSV 证据生成 README / Release 用的 SVG 图。

为什么不用 matplotlib：仓库的卖点之一是"零第三方依赖"，图也应该能一条命令重建。
这里只用标准库，输出纯 SVG（GitHub 直接渲染，放大不糊）。

用法：
    python docs/charts/gen_charts.py

输入全部是 out/ 下已入库的 Multisim COM 导出的原始采样点，不是重画的示意图。
"""
from __future__ import annotations

import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

BG = "#ffffff"
BORDER = "#e2e8f0"
GRID = "#eef2f7"
AXIS = "#cbd5e1"
INK = "#0f172a"
MUTED = "#64748b"
C_IN = "#2563eb"   # 输入
C_OUT = "#dc2626"  # 输出
C_ALT = "#0d9488"
FONT = "'Segoe UI','PingFang SC','Microsoft YaHei','Hiragino Sans GB',sans-serif"


# --------------------------------------------------------------------------- io
def read_csv(rel: str):
    """读 Multisim 导出的波形 CSV，返回 (t, [通道...])。"""
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    t = [float(r[0]) for r in body]
    chans = [[float(r[i]) for r in body] for i in range(1, len(head))]
    return head, t, chans


def thin(t, series, n=700):
    """等步长抽稀到 n 点，避免 SVG 里塞上万条坐标。"""
    if len(t) <= n:
        return t, series
    step = len(t) / n
    idx = sorted({min(len(t) - 1, int(i * step)) for i in range(n)} | {len(t) - 1})
    return [t[i] for i in idx], [[s[i] for i in idx] for s in series]


# ------------------------------------------------------------------------ utils
def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=12, fill=MUTED, weight="400", anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')


def nice_ticks(lo, hi, n=4):
    """按 1/2/2.5/5/10 取整刻度。lo/hi 可能是 1e-3 量级，不能用整数位数推数量级。"""
    span = hi - lo
    if span <= 0:
        return [lo]
    mag = 10 ** math.floor(math.log10(span / n))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if span / step <= n + 1:
            break
    v = math.ceil(lo / step - 1e-9) * step
    ticks = []
    while v <= hi + step * 1e-9:
        ticks.append(round(v, 12))
        v += step
    return ticks


def fmt(v: float) -> str:
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 1:
        return f"{v:g}"
    if a >= 0.001:
        return f"{v:.3g}"
    return f"{v:.2g}"


# ----------------------------------------------------------------------- panels
def panel(x0, y0, w, h, t, series, colors, labels, xmax, ymin, ymax,
          title="", sub="", xlabel="", ylabel="", xunit=1e-3, xtickfmt=None):
    """画一个带网格/坐标轴/图例的折线面板。"""
    out = []
    padl, padr, padt, padb = 46, 12, (34 if title else 12), 30
    px0, py0 = x0 + padl, y0 + padt
    pw, ph = w - padl - padr, h - padt - padb

    def sx(v):
        return px0 + (v / xmax) * pw

    def sy(v):
        return py0 + ph - ((v - ymin) / (ymax - ymin)) * ph

    if title:
        out.append(text(x0 + 2, y0 + 14, title, 13, INK, "600"))
    if sub:
        out.append(text(x0 + 2, y0 + 29, sub, 11, MUTED))

    # 网格 + y 轴刻度
    for v in nice_ticks(ymin, ymax, 4):
        y = sy(v)
        if not (py0 - 0.5 <= y <= py0 + ph + 0.5):
            continue
        out.append(f'<line x1="{px0:.1f}" y1="{y:.1f}" x2="{px0+pw:.1f}" y2="{y:.1f}" '
                   f'stroke="{GRID}" stroke-width="1"/>')
        out.append(text(px0 - 8, y + 4, fmt(v), 10.5, MUTED, anchor="end"))
    # x 轴刻度
    for v in nice_ticks(0, xmax, 5):
        x = sx(v)
        if not (px0 - 0.5 <= x <= px0 + pw + 0.5):
            continue
        lab = xtickfmt(v) if xtickfmt else fmt(v * xunit)
        out.append(text(x, py0 + ph + 16, lab, 10.5, MUTED, anchor="middle"))

    # 坐标轴
    out.append(f'<line x1="{px0}" y1="{py0+ph}" x2="{px0+pw}" y2="{py0+ph}" stroke="{AXIS}"/>')
    out.append(f'<line x1="{px0}" y1="{py0}" x2="{px0}" y2="{py0+ph}" stroke="{AXIS}"/>')
    if ymin < 0 < ymax:  # 零线
        out.append(f'<line x1="{px0}" y1="{sy(0):.1f}" x2="{px0+pw}" y2="{sy(0):.1f}" '
                   f'stroke="{AXIS}" stroke-dasharray="3 3"/>')

    # 曲线
    for s, c in zip(series, colors):
        pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(t, s))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.7" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')

    if xlabel:
        out.append(text(px0 + pw / 2, py0 + ph + 31, xlabel, 10.5, MUTED, anchor="middle"))
    if ylabel:
        out.append(text(px0 - 40, py0 + 10, ylabel, 10.5, MUTED))

    # 图例（标题行右侧）
    if title and labels:
        lx = x0 + w - 4
        for lab, c in reversed(list(zip(labels, colors))):
            tw = 18 + text_width(lab, 11) + 14
            lx -= tw
            out.append(f'<line x1="{lx:.1f}" y1="{y0+11}" x2="{lx+14:.1f}" y2="{y0+11}" '
                       f'stroke="{c}" stroke-width="2.4"/>')
            out.append(text(lx + 18, y0 + 15, lab, 11, MUTED))
            lx -= 6
    return out


def text_width(s: str, size: float) -> float:
    """粗略估宽：CJK/全角按 1.0 em，ASCII 按 0.55 em。只用于图例排版。"""
    return sum(size * (1.0 if ord(ch) > 0x2E80 else 0.55) for ch in s)


def svg(w, h, body, title=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">\n'
            f'<rect width="{w}" height="{h}" rx="10" fill="{BG}" stroke="{BORDER}"/>\n'
            + "\n".join(body) + "\n</svg>\n")


def write(name, s):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)
    print(f"  {name}  {len(s)/1024:.1f} KB")


# ------------------------------------------------------------------------ 图 1
def chart_v020():
    """v0.2.0：分压器中点 2.5 V —— 电阻真的进了网表并导通。"""
    _, t1, c1 = read_csv("out/p0_waveform_source.csv")
    _, t2, c2 = read_csv("out/p0_waveform_divider.csv")
    t, s = thin(t2, [c1[0], c2[0]])
    body = [text(24, 30, "v0.2.0 · 分压器中点实测 2.5 V", 15, INK, "600"),
            text(24, 50, "5 V 电源 + R1/R2 串联到地，探针分别放在源网络与分压中点；2000 个采样点，10 ms 内极差 1.3e-15", 11.5, MUTED)]
    body += panel(24, 62, 832, 250, t, s, [C_IN, C_OUT], ["V(源网络)", "V(分压中点)"],
                  0.010, 0, 6, xlabel="时间 (ms)", ylabel="电压 (V)", xunit=1e3)
    write("v0.2.0-divider.svg", svg(880, 330, body, "v0.2.0 分压器中点 2.5V"))


# ------------------------------------------------------------------------ 图 2
def chart_v030():
    """v0.3.0：一阶 RC 三点频响 —— 电容真的在参与。"""
    cases = [
        ("out/p19_rc_hz100.csv", "100 Hz", "增益 0.995（理论 0.995）· 相位 −5.7°"),
        ("out/p19_rc_main.csv", "1 kHz ≈ fc", "增益 0.706（理论 0.707）· 相位 −45.1°"),
        ("out/p19_rc_hz10k.csv", "10 kHz", "增益 0.100（理论 0.100）· 相位 −84.4°"),
    ]
    body = [text(24, 28, "v0.3.0 · 一阶 RC 低通三点频响（真实 Multisim 采样）", 15, INK, "600"),
            text(24, 47, "R = 1 kΩ，C = 159 nF，fc = 1001 Hz。蓝 = 输入，红 = 输出；三个频率都是真跑仿真，不是推算", 11.5, MUTED)]
    w, gap = 268, 14
    for i, (f, name, note) in enumerate(cases):
        _, t, ch = read_csv(f)
        t, s = thin(t, [ch[0], ch[1]])
        body += panel(24 + i * (w + gap), 62, w, 250, t, s, [C_IN, C_OUT], [], t[-1],
                      -1.15, 1.15, title=name, sub=note,
                      xlabel="ms", ylabel="V" if i == 0 else "", xunit=1e3)
    write("v0.3.0-rc-3freq.svg", svg(880, 340, body, "v0.3.0 一阶 RC 三点频响"))


# ------------------------------------------------------------------------ 图 3
def chart_v050():
    """v0.5.0：直流静态电路，两条取数路径一致。"""
    _, t, ch = read_csv("out/dc/dc_transient_waveform.csv")
    t, s = thin(t, [ch[0], ch[1]])
    body = [text(24, 30, "v0.5.0 · 5 V 直流：V(in) 与 V(0)", 15, INK, "600"),
            text(24, 50, "transient 跑满 1200 点，每个点都是 5.000000 / 0.000000；DoDCOperatingPoint 单点结果完全相同", 11.5, MUTED)]
    body += panel(24, 62, 832, 250, t, s, [C_IN, C_OUT], ["V(探针1) = in", "V(探针2) = 0"],
                  0.006, -1, 6, xlabel="时间 (ms)", ylabel="电压 (V)", xunit=1e3)
    write("v0.5.0-dc.svg", svg(880, 330, body, "v0.5.0 直流静态电路"))


# ------------------------------------------------------------------------ 图 4
def chart_v080():
    """v0.8.0：真 LLM 的两轮任务波形。"""
    body = [text(24, 28, "v0.8.0 · LLM Agent 自己设计的两个电路（真实仿真采样）", 15, INK, "600"),
            text(24, 47, "左：一阶 RC（fc≈500 Hz，Agent 自选 R=10 kΩ / C=33 nF）。右：二阶 RC 梯形（3 网络 / 4 元件 / 2 探针）", 11.5, MUTED),
            text(24, 65, "注意右图：Agent 先放了输出探针，所以「探针1 = 输出、探针2 = 输入」—— 这正是 v0.8.0 修掉的「gain 按探针顺序配对」bug 的现场", 11.5, "#b45309")]
    specs = [
        ("out/agent_v08/p1/evidence/waveform.csv", "任务 1 · 一阶 RC",
         "增益 0.4333（理论 0.4344）· 相位 −64.3°", (0, 1)),
        ("out/agent_v08/p2/evidence/waveform.csv", "任务 2 · 二阶 RC",
         "输出 0.907（理论 0.907）· 先放输出探针", (1, 0)),
    ]
    w, gap = 409, 14
    for i, (f, title, sub, (iin, iout)) in enumerate(specs):
        _, t, ch = read_csv(f)
        t, s = thin(t, [ch[iin], ch[iout]])
        body += panel(24 + i * (w + gap), 80, w, 250, t, s, [C_IN, C_OUT],
                      ["输入", "输出"], t[-1],
                      -1.15, 1.15, title=title, sub=sub,
                      xlabel="时间 (ms)", ylabel="电压 (V)" if i == 0 else "", xunit=1e3)
    write("v0.8.0-agent-waves.svg", svg(880, 358, body, "v0.8.0 LLM Agent 波形"))


# ------------------------------------------------------------------------ 图 5
def chart_v090():
    """v0.9.0：1N4007G 半波整流真机波形。"""
    _, t, ch = read_csv("out/agent_v09/diode/halfwave_1n4007g.csv")
    t, s = thin(t, [ch[0], ch[1]], 900)
    body = [text(24, 30, "v0.9.0 · 1N4007G 半波整流（Agent 自己搭的电路，真实仿真）", 15, INK, "600"),
            text(24, 50, "峰值 4.3696 V · 最小 −0.00010 V · 直流分量 1.3051 V · 导通占比 48.6% · 独立复算深导通压降 0.620 V", 11.5, MUTED)]
    body += panel(24, 62, 832, 250, t, s, [C_IN, C_OUT], ["V(输入)", "V(输出)"],
                  0.1, -5.4, 5.4, xlabel="时间 (ms)", ylabel="电压 (V)", xunit=1e3)
    write("v0.9.0-halfwave.svg", svg(880, 330, body, "v0.9.0 半波整流波形"))


# ------------------------------------------------------------------------ 图 6
def chart_v070():
    """v0.7.0：layout.analyze() 认出来的梯形拓扑（结构示意图，非波形）。"""
    b = [text(24, 30, "v0.7.0 · layout.analyze() 把二阶 RC 认成 ladder（2 级串联 + 2 级到地）", 15, INK, "600"),
         text(24, 50, "三引脚节点 n1 现在是正常的一级，不再是 LAYOUT_UNSUPPORTED；坐标由 plan() 单独算，判断与摆放彻底分开", 11.5, MUTED)]

    def box(x, y, w, h, lab, sub="", fill="#f8fafc", stroke="#94a3b8", tc=INK):
        o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}"/>',
             text(x + w / 2, y + h / 2 + 4, lab, 12.5, tc, "600", "middle")]
        if sub:
            o.append(text(x + w / 2, y + h + 15, sub, 10.5, MUTED, anchor="middle"))
        return o

    def wire(x1, y1, x2, y2, c="#475569"):
        return [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="1.6"/>']

    y = 100
    b += box(60, y, 62, 40, "V1", "源")
    b += wire(122, y + 20, 168, y + 20)
    b += box(168, y, 72, 40, "R1", "串联 1")
    b += wire(240, y + 20, 292, y + 20)
    b += box(292, y, 72, 40, "R2", "串联 2")
    b += wire(364, y + 20, 416, y + 20)
    b += box(416, y, 62, 40, "OUT", "n2")
    # 到地支路
    for cx, lab in ((256, "C1"), (386, "C2")):
        b += [f'<circle cx="{cx}" cy="{y+20}" r="3" fill="#475569"/>']
        b += wire(cx, y + 20, cx, y + 62)
        b += box(cx - 26, y + 62, 52, 38, lab, "", fill="#fef2f2", stroke="#fca5a5", tc="#991b1b")
        b += wire(cx, y + 100, cx, y + 116)
        b += [f'<line x1="{cx-16}" y1="{y+116}" x2="{cx+16}" y2="{y+116}" stroke="#475569" stroke-width="2"/>',
              f'<line x1="{cx-10}" y1="{y+122}" x2="{cx+10}" y2="{y+122}" stroke="#475569" stroke-width="2"/>',
              f'<line x1="{cx-5}" y1="{y+128}" x2="{cx+5}" y2="{y+128}" stroke="#475569" stroke-width="2"/>']
    # 节点标注
    b.append(text(256, y + 12, "n1", 11, "#b45309", "600", "middle"))
    b.append(text(24, 286, 'analyze() → {"kind": "ladder", "n_series": 2, "n_shunt": 2, "out_net": "n2", "supported": true}', 11.5, MUTED))
    b.append(text(24, 310, "同一个 run_task2.py（一行没改）：simulate 从被拒变成跑出数 —— 增益 0.583062（理论 0.584342，误差 −0.219%）", 11.5, MUTED))
    write("v0.7.0-ladder.svg", svg(880, 334, b, "v0.7.0 梯形拓扑"))


# ------------------------------------------------------------------------ 图 7
def chart_pipeline():
    """端到端链路图。"""
    stages = [
        ("①", "一句话需求 / LLM Agent", "中文句子，或一个只读过 MCP tools/list 的模型"),
        ("②", "MCP 工具层（8 个）", "create_circuit / add_component / connect / add_probe / get_circuit / simulate / measure / get_waveform"),
        ("③", "Circuit IR + 拓扑判断", "纯 JSON 描述元件与网络；analyze() 先判拓扑，plan() 再算坐标"),
        ("④", "msbuild 克隆 donor", "从真实 .ms14 里取元件模板，改值、连线、放探针"),
        ("⑤", "生成 .ms14", "PKWARE DCL 压缩 + XML 往返走 mssafe，Multisim 能直接打开"),
        ("⑥", "Multisim 14.3 真仿真", "COM Automation 驱动，读回原始采样点 CSV"),
    ]
    body = [text(24, 30, "端到端链路：从一句话到真实波形", 15, INK, "600"),
            text(24, 50, "每一段都有独立测试；关键结论一律以真实 Multisim 的读数为准", 11.5, MUTED)]
    y = 68
    for i, (num, name, detail) in enumerate(stages):
        body.append(f'<rect x="24" y="{y}" width="832" height="52" rx="8" fill="#f8fafc" stroke="{BORDER}"/>')
        body.append(f'<circle cx="52" cy="{y+26}" r="13" fill="#eff6ff" stroke="#bfdbfe"/>')
        body.append(text(52, y + 30, num, 12, "#1d4ed8", "700", "middle"))
        body.append(text(78, y + 23, name, 13, INK, "600"))
        body.append(text(78, y + 41, detail, 11, MUTED))
        if i < len(stages) - 1:
            body.append(f'<line x1="52" y1="{y+52}" x2="52" y2="{y+61}" stroke="{AXIS}" stroke-width="1.6"/>')
            body.append(f'<path d="M48 {y+58} L52 {y+63} L56 {y+58}" fill="none" stroke="{AXIS}" stroke-width="1.6"/>')
        y += 64
    write("pipeline.svg", svg(880, y + 12, body, "端到端链路"))


# ------------------------------------------------------------------------ 图 8
def chart_v040():
    """v0.4.0：一句中文 → Circuit IR（规则解析，不是 LLM）。"""
    b = [text(24, 28, "v0.4.0 · 一句话直接变成可仿真的电路", 15, INK, "600"),
         text(24, 47, "解析器是规则引擎不是 LLM —— 同一句话永远解析成同一份 IR，否则下游不可复现、回归无从谈起", 11.5, MUTED)]

    # 左：输入
    b.append(f'<rect x="24" y="68" width="330" height="96" rx="8" fill="#f8fafc" stroke="{BORDER}"/>')
    b.append(text(40, 90, "输入（中文）", 11, MUTED, "600"))
    for i, line in enumerate(["1V 1kHz 正弦源，经过 1kΩ 电阻后", "接 159nF 电容到地，", "在输入和输出各放一个探针"]):
        b.append(text(40, 112 + i * 18, line, 12.5, INK))

    # 箭头
    b.append(f'<line x1="356" y1="116" x2="410" y2="116" stroke="{AXIS}" stroke-width="1.8"/>')
    b.append(f'<path d="M404 111 L411 116 L404 121" fill="none" stroke="{AXIS}" stroke-width="1.8"/>')

    # 右：IR 摘要
    b.append(f'<rect x="418" y="68" width="438" height="96" rx="8" fill="#f8fafc" stroke="{BORDER}"/>')
    b.append(text(434, 90, "解析结果（Circuit IR，纯 JSON，不含任何 Multisim 概念）", 11, MUTED, "600"))
    for i, line in enumerate([
        "元件  V1(AC 1V/1kHz)  R1(1kΩ)  C1(159nF)  GND1",
        "网络  in = V1.+ + R1.1      out = R1.2 + C1.1      0 = V1.- + GND1.1 + C1.2",
        "探针  P1@in  P2@out      仿真  transient 0 ~ 6 ms，200 kSa/s",
    ]):
        b.append(text(434, 112 + i * 18, line, 12, INK))

    # 结果条
    b.append(f'<rect x="24" y="182" width="832" height="46" rx="8" fill="#f0fdf4" stroke="#bbf7d0"/>')
    b.append(text(40, 202, "实测（真跑 Multisim 14.3）", 11.5, "#15803d", "600"))
    b.append(text(40, 219, "增益 0.70632（理论 0.70745）· 相位 −45.06°（理论 −44.97°）· 与直接 add_part 的基线 Δ = 0.00e+00", 12, "#166534"))
    b.append(text(24, 252, "缺频率、缺阻值、并联拓扑、白名单外元件 —— 一律报错并说清缺什么，不猜。猜错一个值，电路照样能跑，但结论是错的。", 11.5, MUTED))
    write("v0.4.0-nl2ir.svg", svg(880, 272, b, "v0.4.0 一句话生成电路"))


# ------------------------------------------------------------------------ 图 9
def chart_v060():
    """v0.6.0：8 个有状态关系的 MCP 工具。"""
    b = [text(24, 28, "v0.6.0 · 8 个有状态关系的 MCP 工具", 15, INK, "600"),
         text(24, 47, "Agent 只看到 tools/list 和工具返回；不传坐标、不碰 CiID / CiPort / SimState，布局按拓扑自动算", 11.5, MUTED)]
    tools = ["create_circuit", "add_component", "connect", "add_probe", "simulate", "measure", "get_waveform"]
    w, gap, x = 106, 15, 24
    y = 86
    for i, t in enumerate(tools):
        cx = x + i * (w + gap)
        accent = "#1d4ed8" if i in (0, 4) else "#475569"
        b.append(f'<rect x="{cx}" y="{y}" width="{w}" height="52" rx="8" fill="#f8fafc" stroke="{BORDER}"/>')
        b.append(text(cx + w / 2, y + 22, t, 11, accent, "600", "middle"))
        sub = {0: "建电路 → c-id", 4: "→ sim_id", 5: "增益 / 相位", 6: "原始采样点"}.get(i, "")
        if sub:
            b.append(text(cx + w / 2, y + 39, sub, 10, MUTED, anchor="middle"))
        if i < len(tools) - 1:
            b.append(f'<line x1="{cx+w}" y1="{y+26}" x2="{cx+w+gap}" y2="{y+26}" stroke="{AXIS}" stroke-width="1.5"/>')
            b.append(f'<path d="M{cx+w+gap-5} {y+22} L{cx+w+gap} {y+26} L{cx+w+gap-5} {y+30}" fill="none" stroke="{AXIS}" stroke-width="1.5"/>')
    b.append(f'<rect x="24" y="164" width="832" height="40" rx="8" fill="#eff6ff" stroke="#bfdbfe"/>')
    b.append(text(40, 189, "get_circuit（第 8 个）—— 随时只读取回当前状态，不改变任何东西；探针只有 probe_id 一个身份，measure 与 get_waveform 的键完全一致", 11.5, "#1e40af"))
    b.append(text(24, 232, "错误是结构化返回的：每个错误都带 code / message / hint / context，LLM 接进来之后能自己纠正。", 11.5, MUTED))
    b.append(text(24, 252, "实测：MCP 链路 0.706316 / −45.065° 与中文链路 0.70632 / −45.06° 一致，56 项断言全过（走真实 JSON-RPC 子进程）。", 11.5, MUTED))
    write("v0.6.0-mcp-tools.svg", svg(880, 272, b, "v0.6.0 MCP 工具"))


# ------------------------------------------------------------------------ 图 10
def chart_v100():
    """v0.10.0：同一节点 2 个到地元件（C1 ∥ R2）的真机波形。"""
    _, t, ch = read_csv("out/agent_v10/parallel/case_a_rc_parallel.csv")
    keep = [i for i, ti in enumerate(t) if ti <= 0.0032]
    t = [t[i] for i in keep]
    ch = [[c[i] for i in keep] for c in ch]
    t, s = thin(t, [ch[0], ch[1]], 900)

    body = [text(24, 30, "v0.10.0 · 同一节点 2 个到地元件：C1(159.155nF) ∥ R2(1kΩ)", 15, INK, "600"),
            text(24, 50, "V1 1V/1kHz → R1 1kΩ → n1，n1 上 C1 与 R2 一起下地。实测增益 0.44690（理论 0.44721，−0.07%），相位 −26.65°（理论 −26.57°）", 11.5, MUTED),
            text(24, 68, "反证：如果只有 C1 在网表里，增益会是 0.7071；只有 R2 则是 0.5000。实测 0.4469 只可能来自两者并联", 11.5, "#b45309")]
    body += panel(24, 80, 832, 250, t, s, [C_IN, C_OUT], ["V(输入)", "V(输出)"],
                  0.0032, -1.05, 1.05, xlabel="时间 (ms)", ylabel="电压 (V)",
                  xunit=1e3)
    write("v0.10.0-parallel-shunt.svg",
          svg(880, 340, body, "v0.10.0 并联到地波形"))


if __name__ == "__main__":
    print("生成 SVG：")
    chart_pipeline()
    chart_v020()
    chart_v030()
    chart_v040()
    chart_v050()
    chart_v060()
    chart_v070()
    chart_v080()
    chart_v090()
    chart_v100()
