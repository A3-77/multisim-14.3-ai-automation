# -*- coding: utf-8 -*-
"""单元作业 · 实验任务二：741 反相滞回比较器 + 双向稳压管限幅（图2）。

三种输入条件：
    uim = 5 V,  f = 1 kHz      → 输入跨过两个阈值，输出被削成 ±5.4 V 方波
    uim = 1 V,  f = 1 kHz      → 输入够不着阈值，输出卡在某一侧不翻转
    uim = 5 V,  f = 100 Hz     → 同第一档，只是慢 10 倍，用来做 B/A（X-Y）

图2 的关键细节（放大原图核对过，别改）：
    D1 阴极朝上（接 vout）、阳极朝下；
    D2 **阳极朝上**、阴极朝下接 0 —— 两个稳压管是"阳极对阳极"背靠背串联，
    钳位电压 = ±(4.7 + 0.7) = ±5.4 V。
    同向串联（都阴极朝上）会得到 +9.4 V / −1.4 V 的非对称钳位，那是错的。
    所以 D2 在 IR 里带 rotate=180：符号翻过来，A/K 位置互换。

阈值：U_T = ±Uz·R2/(R1+R2) = ±5.4×0.5 = ±2.7 V。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile          # noqa: E402
import hw_lab1             # noqa: E402  借用 allow_parts()

OUT = os.path.join(ROOT, "out", "hw1")
os.makedirs(OUT, exist_ok=True)

ZENER_DONOR = os.path.join(OUT, "donors", "zener_4v7.ms14")

# 元件坐标 = 引脚质心（引脚偏移见 tools/hw_pins.py 的输出）
POS = {
    "V1":   [100.0, 560.0],    # AC_VOLTAGE   1=(0,-27) 2=(0,27)
    "V2":   [40.0, 300.0],     # DC_POWER +12 1=(0,-18) 2=(0,18)
    "V3":   [150.0, 420.0],    # DC_POWER -12
    "R":    [380.0, 420.0],    # RESISTOR     1=(0,-22.5) 2=(0,22.5)
    "U1":   [700.0, 480.0],    # 741  IN-(656.29,513.43) IN+(656.29,477.43)
    #                            OUT(764.29,495.43) VS+(692.29,441.43) VS-(692.29,549.43)
    "R3":   [940.0, 477.5],    # 1=(940,455)   2=(940,500)
    "D1":   [1090.0, 590.0],   # ZENER  A=(0,27) K=(0,-27) → K 在上
    "D2":   [1090.0, 666.0],   # 同上，再 rotate=180 → A 在上
    "RL":   [1220.0, 590.0],
    "R1":   [1330.0, 590.0],
    "R2":   [1330.0, 680.0],
    "GND1": [1440.0, 880.0],
}

Y_VCC = 120.0      # +12 轨
Y_GND = 880.0      # 地母线
X_FB = 1420.0      # 反馈绕行用的右侧竖线

CASES = [
    ("c1_5v_1k", 5.0, 1000.0, 0.02),
    ("c2_1v_1k", 1.0, 1000.0, 0.02),
    ("c3_5v_100", 5.0, 100.0, 0.05),
]


def allow_zener():
    irmod.SUPPORTED[("ZENER", "02DZ4.7")] = {
        "pins": ("A", "K"), "aliases": {}, "origin": "registry",
        "donor": {"file": ZENER_DONOR, "refdes": "D1"},
    }


def build(uim, freq, tag, with_probes=True, scale=1.0):
    hw_lab1.allow_parts()
    allow_zener()
    ir = irmod.CircuitIR(name="schmitt_%s" % tag)

    def sc(pts):
        return [[p[0] * scale, p[1] * scale] for p in pts]

    def add(ref, fam, part, val=None, params=None, rot=0, vtext=None):
        ir.components.append(irmod.Component(
            refdes=ref, family=fam, part=part, value=val,
            params=params or {}, position=sc([POS[ref]])[0], rotate=rot,
            value_text=vtext))

    add("V1", "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", None,
        {1: uim, 3: 0.0, 5: freq, 7: 0.0})
    add("V2", "POWER_SOURCES", "DC_POWER", 12.0)
    add("V3", "POWER_SOURCES", "DC_POWER", -12.0)
    add("R", "RESISTOR", "RESISTOR_VIRTUAL", 2500.0)
    add("R1", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("R2", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("R3", "RESISTOR", "RESISTOR_VIRTUAL", 300.0)
    add("RL", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("U1", "OPAMP", "741")
    add("D1", "ZENER", "02DZ4.7", vtext="02DZ4.7")
    add("D2", "ZENER", "02DZ4.7", rot=180,      # ← 反接：阳极朝上
        vtext="02DZ4.7")
    add("GND1", "POWER_SOURCES", "GROUND")

    def net(name, pins, route="hv", star=None, routes=None):
        ir.nets.append(irmod.Net(
            name=name, pins=pins, route=route, star=star,
            routes={k: sc(v) for k, v in routes.items()} if routes else None))

    # 输入：V1 上端先竖直到 y=397.5，再横到 R 上端。中间留一个共线折点给探针。
    net("vin", ["V1.1", "R.1"], star="V1.1",
        routes={"R.1": [[160.0, 397.5], [100.0, 397.5]]})

    # R 下端 -> 741 反相输入
    net("n6", ["R.2", "U1.IN-"], route="vh")

    # 741 输出 -> R3（限流）
    net("out", ["U1.OUT", "R3.1"], route="vh")

    # 限幅节点：R3 下端、D1 阴极、RL、R1 上端
    net("vout", ["R3.2", "D1.K", "RL.1", "R1.1"], star="R3.2",
        routes={"D1.K": [[1090.0, 500.0]],
                "RL.1": [[1220.0, 500.0]],
                "R1.1": [[1330.0, 500.0]]})

    # 两只稳压管的公共点（阳极对阳极）
    net("mid", ["D1.A", "D2.A"])

    # 正反馈分压节点：R1 下端 / R2 上端 / 741 同相输入
    # 从同相端出来先向上绕到 y=445，从右侧 x=1420 下来，避开限幅那一列
    net("n2", ["U1.IN+", "R1.2", "R2.1"], star="R1.2",
        routes={"U1.IN+": [[620.0, 477.43], [620.0, 445.0],
                           [X_FB, 445.0], [X_FB, 635.0], [1330.0, 635.0]]})

    net("vcc", ["U1.VS+", "V2.1"], star="U1.VS+",
        routes={"V2.1": [[40.0, Y_VCC], [692.29, Y_VCC]]})
    net("vee", ["U1.VS-", "V3.1"], star="U1.VS-",
        routes={"V3.1": [[220.0, 402.0], [220.0, 549.43]]})

    net("0", ["GND1.1", "V2.2", "V3.2", "V1.2", "D2.K", "RL.2", "R2.2"],
        star="GND1.1",
        routes={"V2.2": [[40.0, Y_GND]],
                "V3.2": [[150.0, Y_GND]],
                "V1.2": [[100.0, Y_GND]],
                "D2.K": [[1090.0, Y_GND]],
                "RL.2": [[1220.0, Y_GND]],
                "R2.2": [[1330.0, Y_GND]]})

    if with_probes:
        # 显式给落点：自动挑点会落在导线拐角上，实测有一次 Multisim 没把它
        # 当输出（EnumOutputs 只回了 1 个）。这两个点都是远离所有引脚的自由拐点。
        ir.probes.append(irmod.Probe(refdes="P_ui", at=sc([[160.0, 397.5]])[0]))
        ir.probes.append(irmod.Probe(refdes="P_uo", at=sc([[1220.0, 500.0]])[0]))

    ir.simulation.analysis = "transient"
    ir.simulation.start = 0.0
    ir.simulation.stop = 0.02 if freq >= 1000 else 0.05
    ir.simulation.step = 5e-6
    ir.simulation.sample_rate = 200000.0
    return ir


def run(tag, uim, freq, stop):
    import ir_sim
    print("\n=== %s  uim=%sV  f=%sHz" % (tag, uim, freq))
    ir = build(uim, freq, tag)
    ms14 = os.path.join(OUT, "schmitt_%s.ms14" % tag)
    rep = ir_compile.compile_ir(ir, ms14, verbose=False)
    print("  编译 %d 字节，探针 %s"
          % (rep["bytes"], [(p["refdes"], p["xy"]) for p in rep["probes"]]))
    res = ir_sim.simulate(ms14, stop=stop, sample_rate=200000.0,
                          timeout=180.0, verbose=False)
    data = res.get("data") or {}
    names = res.get("outputs") or []
    print("  outputs=%s" % names)
    stats = {}
    for nm in names:
        tt, vv = data.get(nm, ([], []))
        if not vv:
            continue
        stats[nm] = {"min": round(min(vv), 4), "max": round(max(vv), 4),
                     "mean": round(sum(vv) / len(vv), 4), "n": len(vv)}
        print("    %-10s min=%.4f max=%.4f mean=%.4f n=%d"
              % (nm, min(vv), max(vv), sum(vv) / len(vv), len(vv)))

    if len(names) == len(ir.probes) and all(n in data for n in names):
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
    return {"tag": tag, "uim": uim, "freq": freq, "stats": stats,
            "ms14": ms14, "outputs": names,
            "probe_xy": [(p["refdes"], p["xy"]) for p in rep["probes"]]}


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    res = []
    for tag, uim, freq, stop in CASES:
        if only and only not in tag:
            continue
        try:
            res.append(run(tag, uim, freq, stop))
        except Exception as e:
            import traceback
            traceback.print_exc()
            res.append({"tag": tag, "error": str(e)})
    path = os.path.join(OUT, "task2_raw.json")
    if only:
        old = []
        if os.path.isfile(path):
            old = [r for r in json.load(open(path, encoding="utf-8"))
                   if r.get("tag") not in {r0.get("tag") for r0 in res}]
        res = old + res
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("\n完成 ->", path)
