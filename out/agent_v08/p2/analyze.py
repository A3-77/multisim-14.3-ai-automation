"""独立分析脚本：只做自己的数学，不 import 任何项目代码。
1) 从波形 CSV 做最小二乘正弦拟合，得到每通道幅值/相位
2) 用复数节点法解析计算二阶 RC 梯形网络的理论传输函数
3) 数值求解 -3dB 截止频率
"""
import csv
import math

# ---------------- 元件参数（设计值，与 Multisim 回读值一致） ----------------
R1, R2 = 1000.0, 10000.0
C1, C2 = 47e-9, 4.7e-9
FS = 1000.0  # 输入频率 Hz


def H(s):
    """复数节点分析：in -R1- mid -R2- out, C1@mid-gnd, C2@out-gnd。"""
    y1 = 1.0 / R1
    y2 = 1.0 / R2
    # 未知量 [Vmid, Vout]，Vin = 1
    # (y1 + sC1 + y2) Vmid - y2 Vout = y1
    # -y2 Vmid + (y2 + sC2) Vout = 0
    a11 = y1 + s * C1 + y2
    a12 = -y2
    a21 = -y2
    a22 = y2 + s * C2
    b1 = y1
    b2 = 0.0
    det = a11 * a22 - a12 * a21
    vout = (a11 * b2 - a21 * b1) / det
    return vout


def mag_phase(f):
    h = H(complex(0.0, 2 * math.pi * f))
    return abs(h), math.degrees(math.atan2(h.imag, h.real))


# ---------------- 二阶参数（由分母系数反推） ----------------
# 分母 = 1 + s*(tau1+tau2+R1C2) + s^2*tau1*tau2
a1 = R1 * C1 + R2 * C2 + R1 * C2
a2 = R1 * C1 * R2 * C2
w0 = 1.0 / math.sqrt(a2)
f0 = w0 / (2 * math.pi)
Q = math.sqrt(a2) / a1

# -3dB 频率：|H| = 1/sqrt(2)，二分法
lo, hi = 1.0, 1e7
for _ in range(200):
    mid = 0.5 * (lo + hi)
    if mag_phase(mid)[0] > 1 / math.sqrt(2):
        lo = mid
    else:
        hi = mid
fc = 0.5 * (lo + hi)

print("=== 理论（解析） ===")
print(f"tau1=R1C1={R1*C1:.6e} s   tau2=R2C2={R2*C2:.6e} s   R1C2={R1*C2:.6e} s")
print(f"a1={a1:.6e}  a2={a2:.6e}")
print(f"f0 (自然频率, Q 定义处) = {f0:.2f} Hz")
print(f"Q = {Q:.4f}")
print(f"fc (-3dB) = {fc:.2f} Hz")

for f in (1000.0, 2000.0, fc):
    m, p = mag_phase(f)
    print(f"  f={f:8.2f} Hz  |H|={m:.6f} ({20*math.log10(m):+.3f} dB)  phase={p:+.3f} deg")

# ---------------- 从 CSV 拟合实际波形 ----------------
PATH = r"C:/Users/A377/WorkBuddy AI/ni/multisim-ctrl/out/mcp/sessions/c-44ba97b68d/sims/s-29160bf3e9.csv"


def fit(rows, col, f, tmin):
    """最小二乘拟合 y = A cos(wt) + B sin(wt) + C，只用 t>=tmin 的稳态段。"""
    w = 2 * math.pi * f
    # 正规方程 3x3
    S = [[0.0] * 3 for _ in range(3)]
    rhs = [0.0] * 3
    n = 0
    for r in rows:
        t = float(r[0])
        if t < tmin:
            continue
        y = float(r[col])
        phi = [math.cos(w * t), math.sin(w * t), 1.0]
        for i in range(3):
            for j in range(3):
                S[i][j] += phi[i] * phi[j]
            rhs[i] += phi[i] * y
        n += 1
    # 高斯消元
    M = [S[i][:] + [rhs[i]] for i in range(3)]
    for i in range(3):
        p = max(range(i, 3), key=lambda k: abs(M[k][i]))
        M[i], M[p] = M[p], M[i]
        for k in range(i + 1, 3):
            fac = M[k][i] / M[i][i]
            for j in range(i, 4):
                M[k][j] -= fac * M[i][j]
    x = [0.0] * 3
    for i in (2, 1, 0):
        s = M[i][3] - sum(M[i][j] * x[j] for j in range(i + 1, 3))
        x[i] = s / M[i][i]
    A, B, C = x
    return math.hypot(A, B), math.degrees(math.atan2(B, A)), C, n


with open(PATH, newline="") as fh:
    rd = list(csv.reader(fh))
hdr = rd[0]
rows = rd[1:]
print(f"\n=== CSV ===\n{hdr}  rows={len(rows)}  t=[{rows[0][0]}, {rows[-1][0]}]")

res = {}
for col, name in ((1, "P_out"), (2, "P_in")):
    for tmin in (0.0, 0.002):
        amp, ph, off, n = fit(rows, col, FS, tmin)
        print(f"{name}  tmin={tmin:.3f}s  n={n:4d}  amp={amp:.6f}  phase={ph:+.4f} deg  dc={off:+.3e}")
        res[(name, tmin)] = (amp, ph)

print("\n=== 实际 vs 理论（1 kHz） ===")
amp_in = res[("P_in", 0.002)][0]
amp_out = res[("P_out", 0.002)][0]
ph_in = res[("P_in", 0.002)][1]
ph_out = res[("P_out", 0.002)][1]
g_act = amp_out / amp_in
g_th, p_th = mag_phase(FS)
print(f"实测 输入幅值 = {amp_in:.6f} V (标称 1.0 V)")
print(f"实测 输出幅值 = {amp_out:.6f} V")
print(f"实测 增益 = {g_act:.6f}   理论增益 = {g_th:.6f}  相对误差 = {(g_act-g_th)/g_th*100:+.3f} %")
# 拟合形式 y=M*cos(wt-phi)，换成 cos 基准相位 theta=-phi；相对相位 = theta_out - theta_in
phase_rel = -(ph_out - ph_in)
print(f"实测 相位 = {phase_rel:+.4f} deg   理论 = {p_th:+.4f} deg  差 = {phase_rel-p_th:+.4f} deg")
print(f"以标称 1V 源计: 输出 {amp_out:.6f} V vs 理论 {g_th*1.0:.6f} V, "
      f"相对 {(amp_out-g_th)/g_th*100:+.3f} %")
print(f"以实测源幅值计: 输出 {amp_out:.6f} V vs 理论 {g_th*amp_in:.6f} V, "
      f"相对 {(amp_out-g_th*amp_in)/(g_th*amp_in)*100:+.3f} %")
print(f"源本身偏差: {amp_in:.6f} vs 1.0 -> {(amp_in-1.0)*100:+.3f} %")
