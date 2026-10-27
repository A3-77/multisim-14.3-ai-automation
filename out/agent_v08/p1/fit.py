import csv, math

CSV = r"C:/Users/A377/WorkBuddy AI/ni/multisim-ctrl/out/mcp/sessions/c-36798c0994/sims/s-22aa89a47f.csv"
F = 1000.0
R = 1000.0
C = 3.3e-7

# ---------- 理论值（完全由我自己推导） ----------
fc = 1.0 / (2.0 * math.pi * R * C)
w = 2.0 * math.pi * F
gain_th = 1.0 / math.sqrt(1.0 + (F / fc) ** 2)
phase_th = -math.degrees(math.atan(F / fc))
print("[theory] fc = %.6f Hz" % fc)
print("[theory] gain = %.9f" % gain_th)
print("[theory] phase = %.6f deg" % phase_th)
print("[theory] Vout_amp = %.9f V" % (1.0 * gain_th))

# ---------- 读 CSV ----------
t, vin, vout = [], [], []
with open(CSV, "r", encoding="utf-8-sig") as fh:
    rd = csv.reader(fh)
    hdr = next(rd)
    for row in rd:
        if len(row) < 3:
            continue
        t.append(float(row[0])); vin.append(float(row[1])); vout.append(float(row[2]))
print("[csv] %s  n=%d  t=[%.6g, %.6g]" % (hdr, len(t), t[0], t[-1]))


def fit(tt, vv, f):
    """最小二乘拟合 v = a*cos(wt) + b*sin(wt) + c"""
    Scc = Sss = Scs = Sc = Ss = S1 = 0.0
    Svc = Svs = Sv = 0.0
    for ti, vi in zip(tt, vv):
        c = math.cos(2 * math.pi * f * ti)
        s = math.sin(2 * math.pi * f * ti)
        Scc += c * c; Sss += s * s; Scs += c * s
        Sc += c; Ss += s; S1 += 1.0
        Svc += vi * c; Svs += vi * s; Sv += vi
    # 3x3 正规方程
    A = [[Scc, Scs, Sc], [Scs, Sss, Ss], [Sc, Ss, S1]]
    B = [Svc, Svs, Sv]
    # 高斯消元
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]; B[i], B[p] = B[p], B[i]
        for r in range(i + 1, 3):
            m = A[r][i] / A[i][i]
            for k in range(i, 3):
                A[r][k] -= m * A[i][k]
            B[r] -= m * B[i]
    x = [0.0, 0.0, 0.0]
    for i in (2, 1, 0):
        x[i] = (B[i] - sum(A[i][k] * x[k] for k in range(i + 1, 3))) / A[i][i]
    a, b, c = x
    return math.hypot(a, b), math.degrees(math.atan2(b, a)), c


def window(t0, t1):
    idx = [i for i, ti in enumerate(t) if t0 - 1e-12 <= ti <= t1 + 1e-12]
    return [t[i] for i in idx], [vin[i] for i in idx], [vout[i] for i in idx]


for label, (t0, t1) in (("full 0-12ms", (0.0, 0.012)), ("steady 8-12ms", (0.008, 0.012))):
    tt, vi, vo = window(t0, t1)
    ai, pi, ci = fit(tt, vi, F)
    ao, po, co = fit(tt, vo, F)
    g = ao / ai
    dp = po - pi
    print("\n[fit %s] n=%d" % (label, len(tt)))
    print("  Vin : amp=%.9f  phase=%.6f deg  dc=%.3e" % (ai, pi, ci))
    print("  Vout: amp=%.9f  phase=%.6f deg  dc=%.3e" % (ao, po, co))
    print("  gain=%.9f  dphase=%.6f deg" % (g, dp))
    print("  err_vs_theory: amp %.4f%%  gain %.4f%%  phase %.4f deg"
          % (100 * (ao - gain_th) / gain_th, 100 * (g - gain_th) / gain_th, dp - phase_th))
