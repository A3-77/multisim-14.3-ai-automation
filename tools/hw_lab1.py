# -*- coding: utf-8 -*-
"""单元作业 · 实验任务一：共射极放大电路（图1）。

按图接线，滑动变阻器 RW 取 10% / 20% / 100% 三档，
每档测 UCE 与 ui/uo 波形。

全部走已验证的 ir_compile -> ir_sim 通道：
    CircuitIR（显式坐标）-> .ms14 -> Multisim 瞬态 -> 读回探针
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile          # noqa: E402

# ir_sim 会 import msc -> pythoncom，只有 32 位 Python 才有；
# 延迟导入，好让 64 位下也能单独跑"只编译不仿真"的离线检查。

OUT = os.path.join(ROOT, "out", "hw1")
os.makedirs(OUT, exist_ok=True)

VCC = 12.0
UIM = 0.010          # 10 mVpk
FREQ = 1000.0

# 元件坐标 = 引脚质心
POS = {
    "V2":   [180.0, 640.0],
    "C1":   [180.0, 500.0],
    "RW":   [520.0, 240.0],
    "RB1":  [520.0, 340.0],
    "RB2":  [520.0, 560.0],
    "Q1":   [700.0, 450.0],
    "RC":   [709.0, 320.0],
    "C2":   [880.0, 414.0],
    "RL":   [1000.0, 550.0],
    "RE":   [709.0, 560.0],
    "CE":   [860.0, 560.0],
    "V1":   [1150.0, 660.0],
    "GND1": [1200.0, 700.0],
}

# 200 kΩ 电位器在 10% / 20% / 100% 位置上的等效电阻。
# 为什么不用真正的 POTENTIOMETER 元件：它的阻值由 Multisim 的交互式 FICL
# 脚本在运行期写进内部 R1/R2，生成出来的文件里那个"百分比"不在 CiaParamList
# 里（8 个 doubles 逐个试过，只有 [5] 是总阻值），仿真读不到设定值。
# 用等效固定电阻在电气上完全等价，而且可复现。
POT_R = {10: 20000.0, 20: 40000.0, 100: 200000.0}

# 本作业要用的元件不在 registry 的 enabled 白名单里（那是给自动布局用的）。
# 这里按需把 spec 直接并进 IR 白名单，不动 registry 配置本身。
_NEED = [
    ("POTENTIOMETER", "POTENTIOMETER_VIRTUAL"),
    ("CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL"),
    ("BJT_NPN", "2N2222A"),
    ("OPAMP", "741"),
    ("ZENER", "1N4734A"),
]


def allow_parts(keys=None):
    import registry as reg
    for key in (keys or _NEED):
        if key in irmod.SUPPORTED:
            continue
        e = reg.spec(*key)
        if not e:
            raise KeyError("registry 里没有 %s" % (key,))
        d = {"pins": tuple(e.get("pins") or ()), "aliases": {},
             "origin": "registry", "spice_template": e.get("spice_template")}
        dpath = reg.donor_path(e)
        if dpath and (e.get("donor") or {}).get("refdes"):
            d["donor"] = {"file": dpath, "refdes": e["donor"]["refdes"]}
        irmod.SUPPORTED[key] = d


def build(pot_pct, tag, with_probes=True, pos=None):
    allow_parts()
    ir = irmod.CircuitIR(name="ce_amp_%s" % tag)
    P = pos or POS

    def add(ref, fam, part, val=None, params=None):
        ir.components.append(irmod.Component(
            refdes=ref, family=fam, part=part, value=val,
            params=params or {}, position=P[ref]))

    add("V1", "POWER_SOURCES", "DC_POWER", VCC)
    add("V2", "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", None,
        {1: UIM, 3: 0.0, 5: FREQ, 7: 0.0})
    add("RW", "RESISTOR", "RESISTOR_VIRTUAL", POT_R[int(pot_pct)])
    add("RB1", "RESISTOR", "RESISTOR_VIRTUAL", 10000.0)
    add("RB2", "RESISTOR", "RESISTOR_VIRTUAL", 10000.0)
    add("RC", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("RE", "RESISTOR", "RESISTOR_VIRTUAL", 1000.0)
    add("RL", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("C1", "CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL", 10e-6)
    add("C2", "CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL", 10e-6)
    add("CE", "CAP_ELECTROLIT", "CAP_ELECTROLIT_VIRTUAL", 47e-6)
    add("Q1", "BJT_NPN", "2N2222A")
    add("GND1", "POWER_SOURCES", "GROUND")

    def net(name, pins, route="hv", tap=False):
        ir.nets.append(irmod.Net(name=name, pins=pins, route=route, tap=tap))

    # +12V：源 -> 电位器等效电阻上端 -> RC 上端
    net("vcc", ["RW.1", "RC.1", "V1.1"])
    # 电位器下端 -> RB1
    net("n6", ["RW.2", "RB1.1"])
    # 基极：RB1 下端 / RB2 上端 / C1 / Q1.B
    net("vb", ["C1.1", "Q1.B", "RB1.2", "RB2.1"])
    # 集电极：RC 下端 / C2 / Q1.C（顺序让探针落在自由拐点上，不压在管脚）
    net("vc", ["RC.2", "C2.1", "Q1.C"])
    # 发射极：Q1.E / RE 上端 / CE 上端
    net("ve", ["Q1.E", "CE.1", "RE.1"])
    # 输出：C2 下端 / RL 上端
    net("vo", ["C2.2", "RL.1"])
    # 输入：V2 上端 / C1 下端（两点直线，探针需要 tap）
    net("vi", ["V2.1", "C1.2"], tap=True)
    # 地
    net("0", ["V2.2", "RB2.2", "RE.2", "CE.2", "RL.2", "V1.2", "GND1.1"],
        route="vh")

    for nm, netname in (("P_vi", "vi"), ("P_vb", "vb"), ("P_vc", "vc"),
                        ("P_ve", "ve"), ("P_vo", "vo")):
        if with_probes:
            ir.probes.append(irmod.Probe(refdes=nm, net=netname, kind="V"))

    ir.simulation.analysis = "transient"
    ir.simulation.start = 0.0
    ir.simulation.stop = 0.20
    ir.simulation.step = 5e-6
    ir.simulation.sample_rate = 200000.0
    return ir


def run(pot_pct, tag, verbose=False):
    import ir_sim
    print("\n=== RW = %s%%" % pot_pct)
    ir = build(pot_pct, tag)
    ms14 = os.path.join(OUT, "ce_amp_%s.ms14" % tag)
    rep = ir_compile.compile_ir(ir, ms14, verbose=verbose)
    print("  编译 %d 字节，探针落点：%s"
          % (rep["bytes"], [(p["refdes"], p["xy"]) for p in rep["probes"]]))
    res = ir_sim.simulate(ms14, stop=0.20, sample_rate=200000.0,
                          timeout=180.0, verbose=False)
    data = res.get("data") or {}
    print("  outputs=%s" % res.get("outputs"))
    out = {}
    for nm, (tt, vv) in data.items():
        if not vv:
            continue
        # 取最后 3 ms 的均值（稳态）
        k = max(1, int(len(vv) * 0.015))
        tail = vv[-k:]
        out[nm] = {"mean": round(sum(tail) / len(tail), 5),
                   "min": round(min(vv), 5), "max": round(max(vv), 5),
                   "n": len(vv)}
        print("    %-10s mean=%.5f min=%.5f max=%.5f n=%d"
              % (nm, out[nm]["mean"], out[nm]["min"], out[nm]["max"], len(vv)))

    # 原始波形落盘，供画图/复核
    names = res.get("outputs") or []
    if names and all(names[i] in data for i in range(len(names))):
        tt = data[names[0]][0]
        cols = [data[n][1] for n in names]
        csvp = os.path.join(OUT, "wave_%s.csv" % tag)
        with open(csvp, "w", encoding="utf-8") as f:
            f.write("t," + ",".join("P%d" % (i + 1) for i in range(len(names)))
                    + "\n")
            for j in range(len(tt)):
                f.write("%.9g," % tt[j]
                        + ",".join("%.9g" % c[j] for c in cols) + "\n")
        print("  波形 -> %s" % csvp)
    return {"pct": pot_pct, "channels": out, "ms14": ms14,
            "probe_xy": [(p["refdes"], p["xy"]) for p in rep["probes"]]}


if __name__ == "__main__":
    print("RW 等效电阻表:", POT_R)
    results = []
    for pct, tag in ((10, "p10"), (20, "p20"), (100, "p100")):
        try:
            results.append(run(pct, tag))
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append({"pct": pct, "error": str(e)})
    with open(os.path.join(OUT, "task1_raw.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n完成 ->", os.path.join(OUT, "task1_raw.json"))
