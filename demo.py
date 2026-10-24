# -*- coding: utf-8 -*-
"""
demo.py —— 端到端演示：打开电路 → 读元件/探针 → 改参数跑多轮仿真 → 出 CSV / 图片 / HTML 报告

演示内容：
  1. 枚举元件、读 R/L/C 值、枚举探针
  2. 在默认值下跑一次瞬态，取时域波形
  3. 把 R7 从 50Ω 扫到 5kΩ，每个值重跑一次，记录稳态输出 —— 得到一条传输特性曲线
  4. 复原 R7，导出 CSV、原理图 PNG、HTML 报告

跑法：
    run.bat demo
"""

import os
import sys
import time
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from msc import Multisim, ImgFmt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SAMPLE = os.path.join(HERE, "samples", "V-I变换2.ms12")
SWEEP_COMP = "R7"
SWEEP_VALUES = [50, 100, 200, 500, 1000, 2000, 5000]


# ------------------------------------------------------------------ 画图
def svg_chart(series, title, ylabel, xlabel, xticks=None, w=760, h=320):
    """极简 SVG 折线图。series: [(名字, x列表, y列表, 颜色)]
    xticks: [(x值, 显示文本)]，给了就按它标 X 轴（用于对数轴/自定义刻度）。"""
    pad_l, pad_r, pad_t, pad_b = 88, 18, 40, 46
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    xs = [x for _, x, _, _ in series for x in x]
    ys = [y for _, _, y, _ in series for y in y]
    if not xs or not ys:
        return "<p style='color:#888'>没有数据</p>"
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x1 = x0 + 1e-9
    if y1 == y0:
        y0, y1 = y0 - abs(y0 or 1) * 0.1, y1 + abs(y1 or 1) * 0.1
    span = y1 - y0
    y0, y1 = y0 - span * 0.1, y1 + span * 0.1

    px = lambda x: pad_l + (x - x0) / (x1 - x0) * iw
    py = lambda y: pad_t + ih - (y - y0) / (y1 - y0) * ih

    out = ['<svg viewBox="0 0 %d %d" width="100%%" style="max-width:%dpx" xmlns="http://www.w3.org/2000/svg">' % (w, h, w)]
    out.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (w, h))
    for i in range(5):
        yy = pad_t + ih * i / 4.0
        val = y1 - (y1 - y0) * i / 4.0
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef0f3"/>' % (pad_l, yy, pad_l + iw, yy))
        out.append('<text x="%d" y="%.1f" font-size="11" fill="#6b7280" text-anchor="end">%.4g</text>' % (pad_l - 8, yy + 4, val))

    if xticks:
        for xv, lab in xticks:
            xx = px(xv)
            out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef0f3"/>' % (xx, pad_t, xx, pad_t + ih))
            out.append('<text x="%.1f" y="%d" font-size="11" fill="#6b7280" text-anchor="middle">%s</text>' % (xx, pad_t + ih + 18, lab))
    else:
        for i in range(5):
            xx = pad_l + iw * i / 4.0
            val = x0 + (x1 - x0) * i / 4.0
            out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef0f3"/>' % (xx, pad_t, xx, pad_t + ih))
            out.append('<text x="%.1f" y="%d" font-size="11" fill="#6b7280" text-anchor="middle">%.4g</text>' % (xx, pad_t + ih + 18, val))

    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#c9ced6"/>' % (pad_l, pad_t + ih, pad_l + iw, pad_t + ih))
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#c9ced6"/>' % (pad_l, pad_t, pad_l, pad_t + ih))

    for name, xv, yv, color in series:
        pts = " ".join("%.1f,%.1f" % (px(x), py(y)) for x, y in zip(xv, yv))
        out.append('<polyline fill="none" stroke="%s" stroke-width="1.9" points="%s"/>' % (color, pts))
        for x, y in zip(xv, yv):
            out.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (px(x), py(y), color))

    out.append('<text x="%d" y="20" font-size="13" font-weight="600" fill="#111827">%s</text>' % (pad_l, title))
    out.append('<text x="15" y="%d" font-size="10.5" fill="#6b7280" text-anchor="middle" transform="rotate(-90 15 %d)">%s</text>' % (pad_t + ih / 2, pad_t + ih / 2, ylabel))
    out.append('<text x="%.1f" y="%d" font-size="11" fill="#6b7280" text-anchor="middle">%s</text>' % (pad_l + iw / 2, h - 6, xlabel))

    lx = pad_l
    for name, _, _, color in series:
        out.append('<line x1="%d" y1="33" x2="%d" y2="33" stroke="%s" stroke-width="2.6"/>' % (lx, lx + 16, color))
        out.append('<text x="%d" y="37" font-size="11" fill="#374151">%s</text>' % (lx + 21, name))
        lx += 40 + 7 * len(name)
    out.append("</svg>")
    return "".join(out)


def human(v):
    """把 0.0001 这类值写成 100u 这种，表格里好读。"""
    a = abs(v)
    if a == 0:
        return "0"
    for div, suf in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p")):
        if a >= div:
            return "%.3g%s" % (v / div, suf)
    return "%.3g" % v


# ------------------------------------------------------------------ 主流程
def main():
    os.makedirs(OUT, exist_ok=True)
    t_start = time.time()

    if not os.path.exists(SAMPLE):
        print("找不到示例电路:", SAMPLE)
        return 1

    with Multisim() as ms:
        print("[1/5] 已连接 %s" % ms.version)
        c = ms.open(SAMPLE)
        comps = c.components()
        probes = c.probes()
        print("      %s | 元件 %d 个 | 探针 %d 个" % (c.name, len(comps), len(probes)))
        if not probes:
            print("      !! 没有探针，取不到数据")
            return 2

        rlc = {}
        for nm in comps:
            try:
                rlc[nm] = c.rlc(nm)
            except Exception:
                pass
        print("      可编程 RLC: %s" % ", ".join("%s=%s" % (k, human(v)) for k, v in rlc.items()))

        print("[2/5] 默认值下跑瞬态，取时域波形")
        wave = c.transient(0.02, sample_rate=10000)
        n = len(next(iter(wave.values()))[0])
        print("      %d 个采样点" % n)

        print("[3/5] 扫 %s：%s Ω" % (SWEEP_COMP, " / ".join(str(v) for v in SWEEP_VALUES)))
        original = c.rlc(SWEEP_COMP)
        sweep = []
        for val in SWEEP_VALUES:
            c.set_rlc(SWEEP_COMP, val)
            d = c.transient(0.005, sample_rate=2000)
            steady = {k: v[1][-1] for k, v in d.items()}
            sweep.append((val, steady))
            print("      %-6s Ω -> %s" % (val, "  ".join("%s=%.4f" % (k, v) for k, v in steady.items())))
        c.set_rlc(SWEEP_COMP, original)
        print("      已复原 %s = %s" % (SWEEP_COMP, human(original)))

        print("[4/5] 导出 CSV / 原理图")
        c.export_csv(os.path.join(OUT, "waveform.csv"), wave)
        with open(os.path.join(OUT, "sweep.csv"), "w", encoding="utf-8-sig") as f:
            keys = list(sweep[0][1])
            f.write("R7_ohm," + ",".join(keys) + "\n")
            for val, st in sweep:
                f.write("%s,%s\n" % (val, ",".join("%.6g" % st[k] for k in keys)))
        png = c.snapshot(os.path.join(OUT, "circuit.png"), ImgFmt.PNG)
        print("      out\\waveform.csv  out\\sweep.csv  %s" % os.path.basename(png))

        print("[5/5] 生成 HTML 报告")
        write_report(os.path.join(OUT, "report.html"), c, wave, sweep, comps, probes, rlc, original)
        print("      out\\report.html")

    print("\n完成，总耗时 %.1f s" % (time.time() - t_start))
    return 0


def write_report(path, circuit, wave, sweep, comps, probes, rlc, original):
    colors = ["#c0392b", "#1f6feb", "#0e9f6e", "#b45309", "#7c3aed", "#0e7490"]

    # 1) 时域波形（电压、电流分开画）
    wave_series = [(nm, wave[nm][0], wave[nm][1], colors[i % len(colors)]) for i, nm in enumerate(probes)]
    vs = [s for s in wave_series if s[0].startswith("V(")]
    iss = [s for s in wave_series if s[0].startswith("I(")]
    wave_charts = []
    if vs:
        wave_charts.append(svg_chart(vs, "时域波形 · 节点电压", "电压 (V)", "时间 (s)"))
    if iss:
        wave_charts.append(svg_chart(iss, "时域波形 · 支路电流", "电流 (A)", "时间 (s)"))

    # 2) 参数扫描曲线（X 用 log10 保证点均匀分布，刻度显示真实阻值）
    import math
    keys = list(sweep[0][1])
    xticks = [(math.log10(v), "%gΩ" % v) for v, _ in sweep]
    lx = [math.log10(v) for v, _ in sweep]
    # 电压和电流量纲差几个数量级，必须分开画，否则电流会贴成一条平线
    groups = [("稳态电压", [k for k in keys if k.startswith("V(")], "电压 (V)"),
              ("稳态电流", [k for k in keys if k.startswith("I(")], "电流 (A)")]
    sweep_charts = []
    for label, ks, unit in groups:
        if not ks:
            continue
        ser = [(k, lx, [st[k] for _, st in sweep], colors[i % len(colors)]) for i, k in enumerate(ks)]
        sweep_charts.append(svg_chart(ser, "%s 参数扫描 · %s" % (SWEEP_COMP, label), unit,
                                      "R7 (Ω)", xticks=xticks))
    sweep_chart = "".join(sweep_charts)

    sweep_rows = "".join(
        "<tr><td>%g</td>%s</tr>" % (v, "".join("<td class='num'>%.4f</td>" % st[k] for k in keys))
        for v, st in sweep)
    sweep_head = "".join("<th>%s</th>" % k for k in keys)

    stats = "".join(
        "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%.6g</td><td class='num'>%.6g</td><td class='num'>%.6g</td></tr>"
        % (nm, len(wave[nm][0]), min(wave[nm][1]), max(wave[nm][1]), sum(wave[nm][1]) / len(wave[nm][1]))
        for nm in probes)

    rlc_rows = "".join("<tr><td>%s</td><td class='num'>%s</td></tr>" % (k, human(v)) for k, v in rlc.items())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Multisim 仿真报告 · %(name)s</title>
<style>
 body{margin:0;background:#f5f6f8;color:#111827;font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
 .wrap{max-width:860px;margin:0 auto;padding:26px 18px 64px}
 h1{font-size:19px;margin:0 0 3px}
 .sub{color:#6b7280;font-size:12px;margin-bottom:20px}
 .card{background:#fff;border:1px solid #e6e8eb;border-radius:10px;padding:16px 18px;margin-bottom:14px}
 .card h2{font-size:13px;margin:0 0 12px;color:#374151;font-weight:600;letter-spacing:.02em}
 table{border-collapse:collapse;width:100%%;font-size:13px}
 th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #f2f4f6}
 th{color:#6b7280;font-weight:500;font-size:12px}
 .num{font-variant-numeric:tabular-nums}
 .kv{display:grid;grid-template-columns:96px 1fr;gap:5px 12px;font-size:13px}
 .kv b{color:#6b7280;font-weight:500}
 img{max-width:100%%;border:1px solid #eef0f3;border-radius:8px}
 code{background:#f3f4f6;padding:1px 5px;border-radius:4px;font-size:12px}
 .note{color:#6b7280;font-size:12px;margin-top:10px}
</style></head><body><div class="wrap">
<h1>Multisim 仿真报告</h1>
<div class="sub">%(now)s · 由 msc.py 通过 Multisim Automation API 自动跑完，全程无人工点击</div>

<div class="card"><h2>电路</h2><div class="kv">
 <b>名称</b><span>%(name)s</span>
 <b>源文件</b><span><code>%(file)s</code></span>
 <b>元件</b><span>%(comps)s</span>
 <b>探针</b><span>%(probes)s</span>
</div></div>

<div class="card"><h2>参数扫描：%(comp)s 从 50Ω 到 5kΩ</h2>
%(sweep_chart)s
<table style="margin-top:10px"><tr><th>%(comp)s (Ω)</th>%(sweep_head)s</tr>%(sweep_rows)s</table>
<div class="note">每换一个阻值都重新跑了一次仿真取稳态值，扫描结束后已把 %(comp)s 复原成 %(orig)s。</div>
</div>

%(wave_cards)s

<div class="card"><h2>探针统计（默认参数下）</h2>
<table><tr><th>探针</th><th>采样点</th><th>最小</th><th>最大</th><th>平均</th></tr>%(stats)s</table></div>

<div class="card"><h2>可编程元件值</h2>
<table><tr><th>位号</th><th>值</th></tr>%(rlc)s</table></div>

<div class="card"><h2>原理图快照</h2><img src="circuit.png" alt="circuit"></div>
</div></body></html>""" % {
        "now": now,
        "name": circuit.name,
        "file": os.path.basename(circuit.file or ""),
        "comps": ", ".join(comps),
        "probes": ", ".join(probes),
        "comp": SWEEP_COMP,
        "sweep_chart": sweep_chart,
        "sweep_head": sweep_head,
        "sweep_rows": sweep_rows,
        "wave_cards": "".join('<div class="card"><h2>时域波形</h2>%s</div>' % ch for ch in wave_charts),
        "stats": stats,
        "rlc": rlc_rows,
        "orig": human(original),
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    sys.exit(main())
