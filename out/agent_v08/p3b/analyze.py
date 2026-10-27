# -*- coding: utf-8 -*-
"""只用标准库：从工具返回的波形 CSV 里算稳态幅值 / 增益 / 相位，并与理论值比较。
CSV 是 get_waveform / simulate 返回的 artifact，属于工具返回值，不是后端内部状态。
"""
import csv, math, cmath, sys

CSV = r"C:/Users/A377/WorkBuddy AI/ni/multisim-ctrl/out/mcp/sessions/c-0a8bdb9b95/sims/s-7116e2f2de.csv"

R = 1000.0        # ohm  (工具回读 R1=1000.0)
C = 1e-7          # F    (工具回读 C1=1e-7)
F0 = 1000.0       # Hz   (V1 frequency)
A0 = 1.0          # V    (V1 amplitude)
W = 2 * math.pi * F0
TAU = R * C

t, vout, vin = [], [], []
with open(CSV, newline="") as f:
    rd = csv.reader(f)
    header = next(rd)
    for row in rd:
        if len(row) < 3:
            continue
        t.append(float(row[0])); vout.append(float(row[1])); vin.append(float(row[2]))

print("header:", header)
print("n =", len(t), " t =", t[0], "..", t[-1], " dt =", t[1]-t[0])

def fit(x, y):
    """最小二乘拟合 y = dc + a*cos(wt) + b*sin(wt)，返回 (dc, amp, phase_deg)"""
    n = len(x)
    s = [math.cos(W*ti) for ti in x]
    c = [math.sin(W*ti) for ti in x]
    # 正规方程 3x3
    S = [[0.0]*3 for _ in range(3)]
    rhs = [0.0]*3
    basis = [[1.0]*n, s, c]
    for i in range(3):
        for j in range(3):
            S[i][j] = sum(basis[i][k]*basis[j][k] for k in range(n))
        rhs[i] = sum(basis[i][k]*y[k] for k in range(n))
    # 高斯消元
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(S[r][i]))
        S[i], S[p] = S[p], S[i]; rhs[i], rhs[p] = rhs[p], rhs[i]
        for r in range(i+1, 3):
            m = S[r][i]/S[i][i]
            for cc in range(i, 3):
                S[r][cc] -= m*S[i][cc]
            rhs[r] -= m*rhs[i]
    sol = [0.0]*3
    for i in (2, 1, 0):
        sol[i] = (rhs[i] - sum(S[i][j]*sol[j] for j in range(i+1, 3)))/S[i][i]
    dc, a, b = sol
    amp = math.hypot(a, b)
    ph = math.degrees(math.atan2(b, a))
    return dc, amp, ph

# 1) 全窗口拟合（含起振段）
dc_a, amp_a, ph_a = fit(t, vout)
print("\n[全窗口 0..%.4g s]" % t[-1])
print("  Vout: dc=%.6g  amp=%.6f  phase=%.3f deg" % (dc_a, amp_a, ph_a))

# 2) 稳态窗口：只取最后 2 个周期（起振已衰减 e^-4 以下）
T = 1.0/F0
sel = [i for i, ti in enumerate(t) if ti >= t[-1] - 2*T]
ts = [t[i] for i in sel]; vs = [vout[i] for i in sel]; is_ = [vin[i] for i in sel]
dc_s, amp_s, ph_s = fit(ts, vs)
dc_i, amp_i, ph_i = fit(ts, is_)
print("\n[稳态窗口 %.4g..%.4g s, %d 点]" % (ts[0], ts[-1], len(ts)))
print("  Vout: dc=%.6g  amp=%.6f  phase=%.3f deg" % (dc_s, amp_s, ph_s))
print("  Vin : dc=%.6g  amp=%.6f  phase=%.3f deg" % (dc_i, amp_i, ph_i))
print("  实测增益 |Vout/Vin| = %.6f   (相位差 %.3f deg)" % (amp_s/amp_i, ph_s - ph_i))

# 3) 每周期峰峰值（(max-min)/2）
print("\n[逐周期 (max-min)/2]")
k = 1
while True:
    lo = (k-1)*T; hi = k*T
    seg = [vout[i] for i, ti in enumerate(t) if lo <= ti < hi]
    if len(seg) < 10:
        break
    print("  周期%d  t=[%.4g,%.4g)  (max-min)/2 = %.6f" % (k, lo, hi, (max(seg)-min(seg))/2))
    k += 1

# 4) 理论值
H = 1/(1 + 1j*W*TAU)
th_amp = A0*abs(H)
th_ph = math.degrees(cmath.phase(H))
fc = 1/(2*math.pi*TAU)
print("\n[理论]")
print("  tau = R*C = %.6g s   fc = 1/(2*pi*R*C) = %.3f Hz" % (TAU, fc))
print("  wRC = %.6f" % (W*TAU))
print("  |H| = 1/sqrt(1+(wRC)^2) = %.6f  -> Vout_amp = %.6f V" % (abs(H), th_amp))
print("  phase = -atan(wRC) = %.3f deg" % th_ph)

# 5) 误差
for name, a in (("全窗口拟合", amp_a), ("稳态拟合", amp_s)):
    print("  [%s] amp=%.6f  abs_err=%.6f V  rel_err=%+.3f %%" %
          (name, a, a-th_amp, (a-th_amp)/th_amp*100))
for name, g in (("稳态拟合", amp_s/amp_i),):
    print("  [%s] gain=%.6f  rel_err=%+.3f %%" % (name, g, (g-abs(H))/abs(H)*100))
