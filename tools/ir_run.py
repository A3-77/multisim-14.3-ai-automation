# -*- coding: utf-8 -*-
"""IR 链路的端到端验收：IR -> .ms14 -> Multisim -> 瞬态 -> COM -> 拟合。

与 tools/validate_rc.py 的区别：
    validate_rc.py  验收的是"直接调用 add_part 拼出来的电路"
    ir_run.py       验收的是"从 Circuit IR 编译出来的电路"

两者必须给出同一个答案 —— 这是 IR 层没有引入偏差的证据。

仿真窗口和采样率取自 IR 的 simulation 块（不是写死的），
所以 IR 里改 stop / sample_rate 会真的改变这次运行。

用法（必须 32 位运行时）：
    runtime\\py32\\python.exe tools\\ir_run.py examples/rc_lowpass.ir.json
"""
import csv
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import circuit_ir as irmod  # noqa: E402
import fitlib              # noqa: E402
import ir_compile          # noqa: E402
import msc                 # noqa: E402

IR_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "examples", "rc_lowpass.ir.json")
OUT_MS14 = os.path.join(ROOT, "out", "ref", "rc_lowpass_ir.ms14")
BASELINE = os.path.join(ROOT, "out", "p19_rc_main.json")

fails = []


def check(name, cond, detail=""):
    print("  %-44s %s%s" % (name, "OK" if cond else "FAIL",
                            ("  " + detail) if detail else ""))
    if not cond:
        fails.append(name)


print("=" * 74)
print("Circuit IR 端到端验收")
print("=" * 74)

# ---------- 0) 读 IR，取出验收需要的量 ----------
c = irmod.CircuitIR.load(IR_PATH)
print("[0] IR: %s" % IR_PATH)
print(c.summary())
print()

src = None
for comp in c.components:
    if comp.family == "SIGNAL_VOLTAGE_SOURCES":
        src = comp
        break
if src is None:
    print("IR 里没有信号源，无法做频响验收")
    sys.exit(4)
freq = float((src.params or {}).get(5) or 0.0)
amp = float(src.value or 0.0)
r_val = next((x.value for x in c.components if x.family == "RESISTOR"), None)
c_val = next((x.value for x in c.components if x.family == "CAPACITOR"), None)
if not freq or r_val is None or c_val is None:
    print("IR 缺少频率 / 电阻 / 电容，无法做频响验收")
    sys.exit(4)
print("  激励 %.6g V @ %.6g Hz   R=%.6g Ω  C=%.6g F  fc=%.1f Hz"
      % (amp, freq, r_val, c_val, fitlib.cutoff(r_val, c_val)))

# ---------- 1) 编译 ----------
print()
print("[1] 编译 IR -> .ms14")
rep = ir_compile.compile_ir(c, OUT_MS14, verbose=True)
check("IR -> .ms14 成功", os.path.exists(OUT_MS14), "%d 字节" % rep["bytes"])
check("探针数量 = IR 声明数", len(rep["probes"]) == len(c.probes),
      "%d / %d" % (len(rep["probes"]), len(c.probes)))

# ---------- 2) 跑仿真 ----------
print()
print("[2] Multisim 瞬态")
sim = c.simulation
stop = float(sim.stop or 0.0)
sr = float(sim.sample_rate or 0.0)
if stop <= 0 or sr <= 0:
    print("IR 的 simulation.stop / sample_rate 非法")
    sys.exit(4)
n = int(min(max(200, stop * sr), 20000))

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
circ = ms.open(OUT_MS14)
outs = list(circ.probes())
print("  outputs: %s" % outs)
check("Multisim 能打开并注册探针", len(outs) >= 2, "%d 个输出" % len(outs))
if len(outs) < 2:
    sys.stdout.flush()
    os._exit(5)

for nm in outs:
    try:
        circ.request_output(nm, sr, n, method=msc.Interp.Linear)
    except Exception as e:
        print("  request_output(%s) 失败: %s" % (nm, e))

circ.run(stop, pause=False)
deadline = time.time() + 40.0
got = ()
while time.time() < deadline:
    try:
        got, _to = circ.wait(500)
    except Exception as e:
        print("  wait 失败: %s" % e)
        break
    if got:
        break
    if circ.state == msc.SimState.Stopped:
        break
print("  state=%s got=%s  window=%gs sr=%gHz n=%d"
      % (circ.state, got, stop, sr, n))
time.sleep(0.5)

data = {}
for nm in outs:
    try:
        t, v = circ.read(nm)
    except Exception as e:
        print("  read(%s) 失败: %s" % (nm, e))
        continue
    if v:
        data[nm] = (list(t), list(v))
        print("  %-12s n=%d  t=[%.6g, %.6g]" % (nm, len(v), t[0], t[-1]))

rlc = {}
for ref in ("R1", "C1"):
    try:
        rlc[ref] = circ.rlc(ref)
    except Exception as e:
        rlc[ref] = None
        print("  RLCValue(%s) 失败: %s" % (ref, e))
try:
    circ.stop()
except Exception:
    pass

# ---------- 3) 拟合 ----------
print()
print("[3] 最小二乘拟合（跳过前 40% 采样，避开起始暂态）")
res = {"ir": IR_PATH, "ms14": OUT_MS14, "freq": freq,
       "rlc": rlc, "channels": {}, "sim": {"stop": stop, "sample_rate": sr, "n": n}}
fits = []
for nm, (t, v) in data.items():
    k0 = int(len(t) * 0.4)
    fit = fitlib.fit_sine(t[k0:], v[k0:], freq)
    if fit is None:
        continue
    a_, ph, off = fit
    res["channels"][nm] = {"amp": a_, "phase_deg": math.degrees(ph), "offset": off}
    fits.append((nm, a_, ph))
    print("  %-12s A=%.5f  φ=%.2f°  偏置=%.5f" % (nm, a_, math.degrees(ph), off))

check("两个通道都读到数据", len(fits) >= 2, "%d 个" % len(fits))
if len(fits) < 2:
    sys.stdout.flush()
    os._exit(6)

# IR 里探针顺序 = 编译序号 = EnumOutputs 顺序，所以 fits[0] 是第一个探针
(n1, a1, p1), (n2, a2, p2) = fits[0], fits[1]
gain = a2 / a1
dph = math.degrees(p2 - p1)
while dph > 180:
    dph -= 360
while dph < -180:
    dph += 360

# 用 IR 里写的元件值算理论值（不是用 Multisim 报回来的），
# 这样"IR 描述的东西"和"仿真的结果"能直接对上
g_th, p_th, _x = fitlib.lowpass_theory(freq, r_val, c_val)
p_th_d = math.degrees(p_th)

# ---------- 4) 判定 ----------
print()
print("[4] 判定")
check("输入幅值 ≈ IR 声明的 %.3g V" % amp, abs(a1 - amp) <= 0.02 * amp,
      "实测 %.5f" % a1)
check("增益 ≈ 理论 |H|=%.5f" % g_th, abs(gain - g_th) <= 0.02,
      "实测 %.5f（误差 %.5f）" % (gain, abs(gain - g_th)))
check("相位 ≈ 理论 ∠H=%.2f°" % p_th_d, abs(dph - p_th_d) <= 3.0,
      "实测 %.2f°（误差 %.2f°）" % (dph, abs(dph - p_th_d)))
check("截止频率在 1 kHz 附近", abs(fitlib.cutoff(r_val, c_val) - 1000.0) < 30,
      "fc=%.1f Hz" % fitlib.cutoff(r_val, c_val))

# ---------- 5) 与直接 add_part 的基线对比 ----------
print()
print("[5] 与直接 add_part 生成的结果对比（%s）"
      % os.path.relpath(BASELINE, ROOT))
base = None
if os.path.exists(BASELINE):
    try:
        base = json.load(open(BASELINE, encoding="utf-8"))
    except Exception as e:
        print("  基线读取失败：%s" % e)
if base:
    dg = abs(gain - base["gain"])
    dp = abs(dph - base["phase_deg"])
    check("增益与基线一致（Δ<=1e-4）", dg <= 1e-4,
          "基线 %.5f  IR %.5f  Δ=%.2e" % (base["gain"], gain, dg))
    check("相位与基线一致（Δ<=0.05°）", dp <= 0.05,
          "基线 %.2f°  IR %.2f°  Δ=%.3f°" % (base["phase_deg"], dph, dp))
    res["baseline"] = {"gain": base["gain"], "phase_deg": base["phase_deg"],
                       "d_gain": dg, "d_phase_deg": dp}
else:
    print("  跳过（基线文件不存在）")

res.update({"gain": gain, "phase_deg": dph,
            "theory_gain": g_th, "theory_phase_deg": p_th_d,
            "pass": not fails})
res["pass"] = not fails

# ---------- 6) 落盘 ----------
os.makedirs(os.path.dirname(OUT_MS14), exist_ok=True)
csv_path = os.path.join(ROOT, "out", "rc_ir_waveform.csv")
names = list(data)
npts = min(len(v) for _t, v in data.values())
with open(csv_path, "w", encoding="utf-8") as f:
    f.write("t," + ",".join(names) + "\n")
    for i in range(npts):
        f.write("%.9g" % data[names[0]][0][i])
        for nm in names:
            f.write(",%.9g" % data[nm][1][i])
        f.write("\n")
res["csv"] = csv_path
jpath = os.path.join(ROOT, "out", "rc_ir_result.json")
with open(jpath, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
    f.write("\n")

print()
print("波形 %s（%d 行）" % (csv_path, npts))
print("结果 %s" % jpath)
print()
print("=" * 74)
print("结论：%s" % ("全部通过" if not fails else "失败项 %s" % fails))
print("=" * 74)
sys.stdout.flush()
os._exit(0 if not fails else 3)
