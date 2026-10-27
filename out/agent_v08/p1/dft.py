import csv, math

CSV = r"C:/Users/A377/WorkBuddy AI/ni/multisim-ctrl/out/mcp/sessions/c-36798c0994/sims/s-22aa89a47f.csv"
t, vin, vout = [], [], []
with open(CSV, "r", encoding="utf-8-sig") as fh:
    rd = csv.reader(fh); next(rd)
    for row in rd:
        if len(row) < 3: continue
        t.append(float(row[0])); vin.append(float(row[1])); vout.append(float(row[2]))

N = 200                      # 每周期采样点数（1kHz @ 200kHz）
start = 1600                 # t = 8 ms，稳态
ncyc = 4
seg = slice(start, start + N * ncyc)
tt = t[seg]; vi = vin[seg]; vo = vout[seg]
print("seg n=%d t=%.6g..%.6g (%.3f cycles)" % (len(tt), tt[0], tt[-1], (tt[-1]-tt[0])*1000))

def dft(v, m):
    """整周期 DFT：m = 窗内该次谐波的周期数（基波 m=ncyc）"""
    n = len(v); re = im = 0.0
    for i, x in enumerate(v):
        th = 2 * math.pi * m * i / n
        re += x * math.cos(th); im += x * math.sin(th)
    re *= 2.0 / n; im *= 2.0 / n
    return math.hypot(re, im), math.degrees(math.atan2(im, re))

for name, v in (("Vin", vi), ("Vout", vo)):
    a1, p1 = dft(v, ncyc)
    print("%s: fund amp=%.9f  phase=%.6f deg  | h2=%.3e h3=%.3e h5=%.3e"
          % (name, a1, p1, dft(v, 2 * ncyc)[0], dft(v, 3 * ncyc)[0], dft(v, 5 * ncyc)[0]))

ai, pi = dft(vi, ncyc); ao, po = dft(vo, ncyc)
print("gain=%.9f   phase_lag=%.6f deg" % (ao / ai, po - pi))
