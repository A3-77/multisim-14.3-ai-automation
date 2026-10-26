# -*- coding: utf-8 -*-
"""正弦拟合与一阶低通理论值（纯计算，无 Multisim 依赖）。

算法与 tools/validate_rc.py 里的完全一致（那支脚本保持原样不动，作为
"直接调用 add_part" 的验收基线）。这里抽出来给 IR 链路复用。

拟合模型：
    y(t) ≈ a·sin(ωt) + b·cos(ωt) + c
    ⇒ 幅值 A = hypot(a, b)，相位 φ = atan2(b, a)，偏置 c

为什么用已知频率 ω 做最小二乘，而不是找峰：
    找峰受采样栅格影响。1 kHz / 200 kHz 采样时，峰值点偏差能让幅值误差到 3%；
    最小二乘把所有采样点都用上，误差能压到 0.1%。
"""
import math


def fit_sine(t, v, f):
    """返回 (幅值, 相位rad, 偏置)；点数不足返回 None。"""
    n = len(t)
    if n < 8:
        return None
    w = 2.0 * math.pi * f
    s11 = s12 = s13 = s22 = s23 = s33 = 0.0
    r1 = r2 = r3 = 0.0
    for ti, vi in zip(t, v):
        st, ct = math.sin(w * ti), math.cos(w * ti)
        s11 += st * st
        s12 += st * ct
        s13 += st
        s22 += ct * ct
        s23 += ct
        s33 += 1.0
        r1 += st * vi
        r2 += ct * vi
        r3 += vi
    m = [[s11, s12, s13, r1],
         [s12, s22, s23, r2],
         [s13, s23, s33, r3]]
    for i in range(3):
        piv = max(range(i, 3), key=lambda k: abs(m[k][i]))
        if abs(m[piv][i]) < 1e-12:
            return None
        m[i], m[piv] = m[piv], m[i]
        pv = m[i][i]
        for j in range(i, 4):
            m[i][j] /= pv
        for k in range(3):
            if k != i and abs(m[k][i]) > 0:
                f2 = m[k][i]
                for j in range(i, 4):
                    m[k][j] -= f2 * m[i][j]
    a, b, c = m[0][3], m[1][3], m[2][3]
    return math.hypot(a, b), math.atan2(b, a), c


def lowpass_theory(f, r, cap):
    """一阶 RC 低通：返回 (|H|, ∠H 弧度, ωRC)。"""
    x = 2.0 * math.pi * f * r * cap
    return 1.0 / math.sqrt(1.0 + x * x), -math.atan(x), x


def cutoff(r, cap):
    return 1.0 / (2.0 * math.pi * r * cap)
