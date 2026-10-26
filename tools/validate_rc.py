# -*- coding: utf-8 -*-
"""P19：RC 低通瞬态验证 —— 拟合幅值/相位，和理论值比对。

判定依据不是"看起来像正弦"，而是：
    |H|  = A_out / A_in            应等于 1/sqrt(1+(ωRC)²)
    ∠H   = φ_out - φ_in            应等于 -atan(ωRC)

方法：对每个探针通道做最小二乘正弦拟合
        y(t) ≈ a·sin(ωt) + b·cos(ωt) + c
    则幅值 A = hypot(a, b)，相位 φ = atan2(b, a)。
    用已知激励频率 ω 拟合，而不是靠找峰，避免采样栅格误差。

用法（必须用 32 位运行时）：
    runtime\\py32\\python.exe tools\\validate_rc.py out/ref/rc_lowpass.ms14 1000 main
产物：
    out/p19_rc_<label>.csv   两个通道的原始波形
    out/p19_rc_<label>.json  拟合结果与判定
"""
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = sys.argv[1]
FREQ = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
LABEL = sys.argv[3] if len(sys.argv) > 3 else "main"
CYCLES = 6.0
SR = 200000.0


def fit_sine(t, v, f):
    """最小二乘拟合 y = a·sin(ωt) + b·cos(ωt) + c，返回 (幅值, 相位rad, 偏置)。"""
    w = 2.0 * math.pi * f
    n = len(t)
    if n < 8:
        return None
    # 正规方程（3x3），手工解，避免引入 numpy 依赖
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
    # 解 [s11 s12 s13; s12 s22 s23; s13 s23 s33] x = [r1 r2 r3]
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


def theory(f, r, cap):
    w = 2.0 * math.pi * f
    x = w * r * cap
    return 1.0 / math.sqrt(1.0 + x * x), -math.atan(x), x


subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)
outs = list(c.probes())
print("outputs:", outs)
if len(outs) < 2:
    print("探针数不足 2，无法比较输入/输出")
    sys.stdout.flush()
    os._exit(4)

dur = CYCLES / FREQ
# 采样点数：至少 2000，但不无限增长（100 Hz 跑 6 个周期会到 12000 点，
# CSV 400 KB 没必要）。上限 4000 点，低频时每个周期仍有 600+ 点。
n = int(min(max(2000, dur * SR), 4000))
for nm in outs:
    try:
        c.request_output(nm, SR, n, method=msc.Interp.Linear)
    except Exception as e:
        print("request %s 失败: %s" % (nm, e))

c.run(dur, pause=False)
deadline = time.time() + 40.0
got = ()
while time.time() < deadline:
    try:
        got, _to = c.wait(500)
    except Exception as e:
        print("wait 失败:", e)
        break
    if got:
        break
    if c.state == msc.SimState.Stopped:
        break
print("state=%s got=%s" % (c.state, got))
time.sleep(0.5)

data = {}
for nm in outs:
    try:
        t, v = c.read(nm)
    except Exception as e:
        print("%-12s 读取失败: %s" % (nm, e))
        continue
    if v:
        data[nm] = (list(t), list(v))
        print("%-12s n=%d  t=[%.6g, %.6g]" % (nm, len(v), t[0], t[-1]))

# 元件实际值（Multisim 自己报的，不是我们写的）
rlc = {}
for ref in ("R1", "C1"):
    try:
        rlc[ref] = c.rlc(ref)
    except Exception as e:
        rlc[ref] = None
        print("RLCValue(%s) 失败: %s" % (ref, e))

try:
    c.stop()
except Exception:
    pass

# ---- 拟合（只用后 60% 采样，避开起始暂态）----
res = {"src": SRC, "freq": FREQ, "label": LABEL, "cycles": CYCLES,
       "rlc": rlc, "channels": {}}
fits = []
for nm, (t, v) in data.items():
    k0 = int(len(t) * 0.4)
    fit = fit_sine(t[k0:], v[k0:], FREQ)
    if fit is None:
        continue
    amp, ph, off = fit
    res["channels"][nm] = {"amp": amp, "phase_deg": math.degrees(ph), "offset": off,
                           "n_used": len(t) - k0}
    fits.append((nm, amp, ph))
    print("%-12s A=%.5f  φ=%.2f°  偏置=%.5f" % (nm, amp, math.degrees(ph), off))

# ---- 判定 ----
ok = False
if len(fits) >= 2:
    (n1, a1, p1), (n2, a2, p2) = fits[0], fits[1]
    gain = a2 / a1
    dph = math.degrees(p2 - p1)
    while dph > 180:
        dph -= 360
    while dph < -180:
        dph += 360
    r = rlc.get("R1") or 1000.0
    cap = rlc.get("C1") or 159e-9
    g_th, p_th, x = theory(FREQ, r, cap)
    p_th_d = math.degrees(p_th)
    res.update({"gain": gain, "phase_deg": dph,
                "theory_gain": g_th, "theory_phase_deg": p_th_d,
                "fc": 1.0 / (2 * math.pi * r * cap), "wrc": x})
    eg, ep = abs(gain - g_th), abs(dph - p_th_d)
    ok = eg <= 0.02 and ep <= 3.0
    res["err_gain"], res["err_phase_deg"], res["pass"] = eg, ep, ok
    print()
    print("R1=%.4g Ω  C1=%.6g F  →  fc=%.1f Hz" % (r, cap, 1.0 / (2 * math.pi * r * cap)))
    print("增益 实测 %.5f / 理论 %.5f  误差 %.5f  (限 0.02)"
          % (gain, g_th, eg))
    print("相位 实测 %.2f° / 理论 %.2f°  误差 %.2f°  (限 3°)"
          % (dph, p_th_d, ep))
    print("判定:", "通过" if ok else "不通过")

# ---- 导出 ----
csv = os.path.join(ROOT, "out", "p19_rc_%s.csv" % LABEL)
with open(csv, "w", encoding="utf-8") as f:
    names = list(data)
    npts = min(len(v) for _t, v in data.values())
    f.write("t," + ",".join(names) + "\n")
    for i in range(npts):
        f.write("%.9g" % data[names[0]][0][i])
        for nm in names:
            f.write(",%.9g" % data[nm][1][i])
        f.write("\n")
res["csv"] = csv
print("波形已写 %s（%d 行 × %d 列）" % (csv, npts, len(names) + 1))

j = os.path.join(ROOT, "out", "p19_rc_%s.json" % LABEL)
with open(j, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print("结果已写", j)
sys.stdout.flush()
os._exit(0 if ok else 3)
