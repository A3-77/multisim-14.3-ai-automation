import csv, math

CSV = r"C:/Users/A377/WorkBuddy AI/ni/multisim-ctrl/out/mcp/sessions/c-36798c0994/sims/s-22aa89a47f.csv"
t, vin, vout = [], [], []
with open(CSV, "r", encoding="utf-8-sig") as fh:
    rd = csv.reader(fh); next(rd)
    for row in rd:
        if len(row) < 3: continue
        t.append(float(row[0])); vin.append(float(row[1])); vout.append(float(row[2]))

idx = [i for i, ti in enumerate(t) if 0.008 <= ti <= 0.012]
vi = [vin[i] for i in idx]; vo = [vout[i] for i in idx]; tt = [t[i] for i in idx]
print("steady window n=%d  t=%.6g..%.6g" % (len(idx), tt[0], tt[-1]))
print("Vin  min/max = %.9f / %.9f  pk-pk=%.9f" % (min(vi), max(vi), max(vi) - min(vi)))
print("Vout min/max = %.9f / %.9f  pk-pk=%.9f" % (min(vo), max(vo), max(vo) - min(vo)))
print("Vout (max-min)/2 = %.9f" % ((max(vo) - min(vo)) / 2))
rms_i = math.sqrt(sum(v * v for v in vi) / len(vi))
rms_o = math.sqrt(sum(v * v for v in vo) / len(vo))
print("RMS Vin=%.9f Vout=%.9f  rms_gain=%.9f" % (rms_i, rms_o, rms_o / rms_i))

# 由输入上升过零点测频率
cross = []
for k in range(1, len(tt)):
    if vin[idx[k - 1]] < 0 <= vin[idx[k]]:
        x0, x1 = tt[k - 1], tt[k]; y0, y1 = vin[idx[k - 1]], vin[idx[k]]
        cross.append(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))
print("rising zero crossings:", ["%.6f" % c for c in cross])
if len(cross) > 1:
    per = (cross[-1] - cross[0]) / (len(cross) - 1)
    print("measured period = %.9f s -> f = %.4f Hz" % (per, 1 / per))
print("time step = %.3e s (uniform=%s)" % (t[1] - t[0], all(abs((t[i+1]-t[i]) - (t[1]-t[0])) < 1e-12 for i in range(len(t)-1))))
