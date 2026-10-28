# -*- coding: utf-8 -*-
"""v0.9.2 独立验收器 —— 只读 waveform.csv，自己算，不采信 Agent 的 measure。

设计约束（对应规格 §9 / §3.2）：
  * **不认 Case**：没有 "if case == 'B'" 这种分支。要验什么由 spec.json 声明。
  * **不含设计答案**：spec 里只有"需求指标 + 容差"，没有拓扑名、元件名、位号。
  * **不碰项目内部模块**：只用标准库解析 CSV 做数学，连 ir_sim / circuit_session
    都不 import —— 否则就不独立了。

用法：
    python tools/agent_acceptance/verify_v092.py <spec.json> <waveform.csv> [out.json]

spec.json:
{
  "mode": "sine_gain" | "rectifier",
  "in_col": 1, "out_col": 2,          # CSV 列号（0 是时间）
  "checks": {
     "input_peak":   {"target": 1.0, "tol_pct": 10},
     "input_freq_hz":{"target": 1000, "tol_pct": 2},
     "gain":         {"target": 0.5, "tol_pct": 20},
     "cutoff_hz":    {"target": 500, "tol_pct": 10}
  }
}
rectifier 模式可用：input_peak / input_freq_hz / neg_ratio_max / pos_ratio_min
"""
from __future__ import annotations

import csv
import json
import math
import sys


# ---------------------------------------------------------------- 读数据
def read_csv(path, in_col, out_col):
    t, vi, vo = [], [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.reader(f)
        header = next(rd)
        for row in rd:
            if len(row) <= max(in_col, out_col):
                continue
            try:
                t.append(float(row[0]))
                vi.append(float(row[in_col]))
                vo.append(float(row[out_col]))
            except ValueError:
                continue
    if len(t) < 20:
        raise ValueError("样本太少：%d" % len(t))
    return header, t, vi, vo


def _mean(xs):
    return sum(xs) / len(xs)


def freq_from_zero_crossings(t, v):
    """上升过零点间隔推频率（线性插值，抗采样相位）。"""
    m = _mean(v)
    d = [x - m for x in v]
    cross = []
    for i in range(1, len(d)):
        if d[i - 1] < 0.0 <= d[i]:
            # 线性插值定位过零时刻
            denom = d[i] - d[i - 1]
            frac = (-d[i - 1] / denom) if denom else 0.0
            cross.append(t[i - 1] + frac * (t[i] - t[i - 1]))
    if len(cross) < 2:
        return None, len(cross)
    periods = [cross[i] - cross[i - 1] for i in range(1, len(cross))]
    per = _mean(periods)
    return (1.0 / per if per > 0 else None), len(cross)


def sine_fit(t, v, f):
    """v(t) ≈ A·sin(2πft) + B·cos(2πft) + C，返回 (amp, phase_deg, rms_resid)。

    3×3 正规方程手写求解 —— 环境里没有 numpy，也不该为验收引入依赖。
    """
    n = len(t)
    w = 2.0 * math.pi * f
    s = [math.sin(w * x) for x in t]
    c = [math.cos(w * x) for x in t]
    # 未知量 [A, B, C]
    ss = sum(x * x for x in s)
    cc = sum(x * x for x in c)
    sc = sum(a * b for a, b in zip(s, c))
    s1 = sum(s)
    c1 = sum(c)
    sy = sum(a * b for a, b in zip(s, v))
    cy = sum(a * b for a, b in zip(c, v))
    y1 = sum(v)
    M = [[ss, sc, s1], [sc, cc, c1], [s1, c1, float(n)]]
    r = [sy, cy, y1]
    # 高斯消元
    for i in range(3):
        p = max(range(i, 3), key=lambda k: abs(M[k][i]))
        if abs(M[p][i]) < 1e-18:
            return None, None, None
        M[i], M[p] = M[p], M[i]
        r[i], r[p] = r[p], r[i]
        for k in range(i + 1, 3):
            fac = M[k][i] / M[i][i]
            for j in range(i, 3):
                M[k][j] -= fac * M[i][j]
            r[k] -= fac * r[i]
    x = [0.0, 0.0, 0.0]
    for i in (2, 1, 0):
        acc = r[i] - sum(M[i][j] * x[j] for j in range(i + 1, 3))
        x[i] = acc / M[i][i]
    A, B, C = x
    amp = math.hypot(A, B)
    phase = math.degrees(math.atan2(B, A))     # v = amp·sin(wt + phase)
    resid = 0.0
    for k in range(n):
        pred = A * s[k] + B * c[k] + C
        resid += (v[k] - pred) ** 2
    return amp, phase, math.sqrt(resid / n)


# ---------------------------------------------------------------- 判据
def judge(name, value, spec, results):
    if value is None:
        results.append({"name": name, "value": None, "pass": False,
                        "reason": "算不出来"})
        return
    target = spec["target"]
    tol = spec.get("tol_pct", 5.0)
    err = (value - target) / target * 100.0 if target else None
    ok = err is not None and abs(err) <= tol
    results.append({"name": name, "value": round(value, 6), "target": target,
                    "tol_pct": tol, "err_pct": round(err, 3) if err is not None else None,
                    "pass": ok})


def judge_max(name, value, limit, results):
    """value 必须 ≤ limit（负半周抑制这类）。"""
    ok = value is not None and value <= limit
    results.append({"name": name, "value": round(value, 6) if value is not None else None,
                    "max_allowed": limit, "pass": ok})


def judge_min(name, value, limit, results):
    ok = value is not None and value >= limit
    results.append({"name": name, "value": round(value, 6) if value is not None else None,
                    "min_required": limit, "pass": ok})


# ---------------------------------------------------------------- 主流程
def verify(spec, csv_path):
    mode = spec.get("mode", "sine_gain")
    in_col = spec.get("in_col", 1)
    out_col = spec.get("out_col", 2)
    header, t, vi, vo = read_csv(csv_path, in_col, out_col)

    f_in, n_cross = freq_from_zero_crossings(t, vi)
    checks = spec.get("checks", {})
    results = []
    measured = {
        "csv": csv_path,
        "columns": header,
        "n_samples": len(t),
        "t_range": [t[0], t[-1]],
        "input_freq_hz": round(f_in, 4) if f_in else None,
        "input_zero_crossings": n_cross,
        "input_peak_v": round(max(vi) - min(vi), 6),
        "input_min_v": round(min(vi), 6),
        "input_max_v": round(max(vi), 6),
        "output_min_v": round(min(vo), 6),
        "output_max_v": round(max(vo), 6),
        "output_mean_v": round(_mean(vo), 6),
    }

    if "input_freq_hz" in checks:
        judge("input_freq_hz", f_in, checks["input_freq_hz"], results)
    if "input_peak" in checks:
        judge("input_peak", (max(vi) - min(vi)) / 2.0, checks["input_peak"], results)

    if mode == "sine_gain":
        # 只拟合稳态段：t=0 起有 RC 充电暂态，混进去会把相位拉偏几度。
        skip = spec.get("skip_frac", 0.0)
        k0 = int(len(t) * skip)
        ts, vis, vos = t[k0:], vi[k0:], vo[k0:]
        amp_in, ph_in, r_in = sine_fit(ts, vis, f_in) if f_in else (None, None, None)
        amp_out, ph_out, r_out = sine_fit(ts, vos, f_in) if f_in else (None, None, None)
        gain = (amp_out / amp_in) if (amp_in and amp_out) else None
        phase = (ph_out - ph_in) if (ph_in is not None and ph_out is not None) else None
        measured.update({
            "fit_skip_frac": skip,
            "fit_samples": len(ts),
            "input_amp_v": round(amp_in, 6) if amp_in else None,
            "output_amp_v": round(amp_out, 6) if amp_out else None,
            "gain": round(gain, 6) if gain else None,
            "phase_deg": round(phase, 4) if phase is not None else None,
            "fit_residual_in": round(r_in, 6) if r_in is not None else None,
            "fit_residual_out": round(r_out, 6) if r_out is not None else None,
        })
        if "gain" in checks:
            judge("gain", gain, checks["gain"], results)
        if "cutoff_hz" in checks:
            # 一阶低通：fc = f / sqrt(1/gain² − 1)；gain≥1 时无意义
            fc = None
            if gain and 0 < gain < 1:
                fc = f_in / math.sqrt(1.0 / (gain * gain) - 1.0)
            measured["cutoff_hz_derived"] = round(fc, 3) if fc else None
            judge("cutoff_hz", fc, checks["cutoff_hz"], results)

    elif mode == "rectifier":
        peak = (max(vi) - min(vi)) / 2.0
        neg_ratio = (abs(min(vo)) / peak) if peak else None
        pos_ratio = (max(vo) / peak) if peak else None
        frac_neg = sum(1 for x in vo if x < -0.1 * peak) / float(len(vo))
        measured.update({
            "neg_ratio": round(neg_ratio, 6) if neg_ratio is not None else None,
            "pos_ratio": round(pos_ratio, 6) if pos_ratio is not None else None,
            "frac_samples_below_-10pct_peak": round(frac_neg, 6),
        })
        if "neg_ratio_max" in checks:
            judge_max("neg_ratio", neg_ratio, checks["neg_ratio_max"], results)
        if "pos_ratio_min" in checks:
            judge_min("pos_ratio", pos_ratio, checks["pos_ratio_min"], results)
    else:
        raise ValueError("未知 mode：%r" % mode)

    return {
        "independent": True,
        "method": "从 waveform.csv 原始采样点重算（过零点测频 + 最小二乘正弦拟合）",
        "mode": mode,
        "measured": measured,
        "criteria": results,
        "pass": all(x["pass"] for x in results) and bool(results),
    }


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    spec = json.load(open(argv[1], encoding="utf-8"))
    out = verify(spec, argv[2])
    if len(argv) > 3:
        with open(argv[3], "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
