import csv, math

R, C, f, Vs = 1000.0, 100e-9, 2000.0, 1.0
w = 2 * math.pi * f
fc = 1.0 / (2 * math.pi * R * C)
H = 1.0 / (1.0 + 1j * w * R * C)
th_gain = abs(H)
th_phase = math.degrees(math.atan2(H.imag, H.real))
th_amp = Vs * th_gain

a_out, a_in = 0.6194638674718141, 0.996793694693477
ph_out, ph_in = -51.57827392044402, -0.00024914585442332136
gain, phase = a_out / a_in, ph_out - ph_in

path = r"C:/Users/A377/WorkBuddy AI/ni/multisim-ctrl/out/mcp/sessions/c-7ee828f13d/sims/s-6f3a22498e.csv"
rows = list(csv.reader(open(path, encoding="utf-8-sig")))
t = [float(r[0]) for r in rows[1:]]
v1 = [float(r[1]) for r in rows[1:]]
v2 = [float(r[2]) for r in rows[1:]]


def fit(tt, vv, freq):
    ww = 2 * math.pi * freq
    n = len(tt)
    S1 = sum(math.sin(ww * x) for x in tt)
    C1 = sum(math.cos(ww * x) for x in tt)
    CC = sum(math.cos(ww * x) ** 2 for x in tt)
    SS = sum(math.sin(ww * x) ** 2 for x in tt)
    CS = sum(math.cos(ww * x) * math.sin(ww * x) for x in tt)
    Sv = sum(vv)
    Sc = sum(v * math.cos(ww * x) for x, v in zip(tt, vv))
    Ss = sum(v * math.sin(ww * x) for x, v in zip(tt, vv))
    M = [[n, C1, S1, Sv], [C1, CC, CS, Sc], [S1, CS, SS, Ss]]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        for r in range(3):
            if r != i:
                fac = M[r][i] / M[i][i]
                for k in range(i, 4):
                    M[r][k] -= fac * M[i][k]
    dc, a, b = [M[i][3] / M[i][i] for i in range(3)]
    return dc, math.hypot(a, b), math.degrees(math.atan2(b, a))


start = t[0] + 1.0 / f
idx = [i for i in range(len(t)) if t[i] >= start]
dc1, amp1, ph1 = fit([t[i] for i in idx], [v1[i] for i in idx], f)
dc2, amp2, ph2 = fit([t[i] for i in idx], [v2[i] for i in idx], f)

print("theory: fc=%.4f Hz  wRC=%.6f" % (fc, w * R * C))
print("theory: gain=%.6f  phase=%.4f deg  amp=%.6f V" % (th_gain, th_phase, th_amp))
print()
print("tool : amp_out=%.9f amp_in=%.9f  ph_out=%.6f ph_in=%.6f" % (a_out, a_in, ph_out, ph_in))
print("tool : gain=%.6f phase=%.6f" % (gain, phase))
print("tool : rms_out=0.44226470022239883 -> amp/sqrt2 = %.6f" % (0.44226470022239883 * math.sqrt(2)))
print()
print("csv  : out dc=%.3e amp=%.6f phase=%.4f" % (dc1, amp1, ph1))
print("csv  : in  dc=%.3e amp=%.6f phase=%.4f" % (dc2, amp2, ph2))
print("csv  : gain=%.6f phase=%.4f" % (amp1 / amp2, ph1 - ph2))
print()
print("err  : gain %+.6f (%+.4f %%)" % (gain - th_gain, (gain - th_gain) / th_gain * 100))
print("err  : phase %+.6f deg (%+.4f %%)" % (phase - th_phase, (phase - th_phase) / abs(th_phase) * 100))
print("err  : amp %+.6f V (%+.4f %%)" % (a_out - th_amp, (a_out - th_amp) / th_amp * 100))
print("err  : csv-vs-tool gain %+.6f  amp %+.6f  phase %+.4f" % (amp1 / amp2 - gain, amp1 - a_out, ph1 - ph_out))
