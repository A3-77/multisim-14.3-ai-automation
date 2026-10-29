# -*- coding: utf-8 -*-
"""acmodel.py 的纯逻辑测试（不需要 Multisim，任意位数 Python）。

这一层测的是**理论值本身对不对**，不是"代码和代码一致"：
每个期望值都是能手算的整数关系，写在注释里。

    一阶 RC @ 截止频率      |H| = 1/√2, ∠-45°          （k = ωRC = 1）
    二阶 RC 梯形 @ k = 1    |H| = 1/3,  ∠-90°           （1/(1-k²+3jk)）
    R1 串联 + (R2 ∥ C1)     |H| = 0.4472, ∠-26.565°     （Z = 500-j500）
    纯电阻并联             没有频率 → None（不给假数）
    含二极管               没有线性模型 → None
    只有一个到地元件        退化成普通分压（回归：v0.1~v0.9 的电路）

跑法：
    python tools/test_acmodel.py
"""
import cmath
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import acmodel as A      # noqa: E402
import circuit_ir as irmod  # noqa: E402

npass = 0
nfail = 0

AC = ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE")
DC = ("POWER_SOURCES", "DC_POWER")
R = ("RESISTOR", "RESISTOR_VIRTUAL")
C = ("CAPACITOR", "CAPACITOR_VIRTUAL")
G = ("POWER_SOURCES", "GROUND")

F = 1000.0
# 让 ωRC 正好等于 1 的电容值：C = 1/(2πfR)
C_1K = 1.0 / (2.0 * math.pi * F * 1000.0)     # ≈ 159.155 nF


def check(name, cond, detail=""):
    global npass, nfail
    if cond:
        npass += 1
        print("  %-52s OK   %s" % (name, detail))
    else:
        nfail += 1
        print("  %-52s FAIL %s" % (name, detail))


def build(name, comps, nets):
    ir = irmod.CircuitIR(name=name)
    for ref, key, val, params in comps:
        ir.components.append(irmod.Component(refdes=ref, family=key[0],
                                             part=key[1], value=val,
                                             params=params or {}))
    for nm, pins in nets:
        ir.nets.append(irmod.Net(name=nm, pins=list(pins)))
    return ir


def near(a, b, tol=1e-4):
    return a is not None and abs(a - b) <= tol


def ir_bypass():
    """V1 - R1 - n1 - C1 - 0，ωRC = 1。"""
    return build("bypass",
                 [("V1", AC, 1.0, {5: F}), ("R1", R, 1000.0, None),
                  ("C1", C, C_1K, None), ("GND1", G, None, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "C1.1"]),
                  ("0", ["C1.2", "V1.2", "GND1.1"])])


def ir_parallel():
    """V1 - R1 - n1，n1 上 C1 ∥ R2 一起下地。"""
    return build("rc_parallel",
                 [("V1", AC, 1.0, {5: F}), ("R1", R, 1000.0, None),
                  ("R2", R, 1000.0, None), ("C1", C, C_1K, None),
                  ("GND1", G, None, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "R2.1", "C1.1"]),
                  ("0", ["R2.2", "C1.2", "V1.2", "GND1.1"])])


def ir_ladder2():
    """两节完全相同的 RC 梯形，ωRC = 1 → H = 1/(1-k²+3jk) = 1/(3j)。"""
    return build("ladder2",
                 [("V1", AC, 1.0, {5: F}), ("R1", R, 1000.0, None),
                  ("R2", R, 1000.0, None), ("C1", C, C_1K, None),
                  ("C2", C, C_1K, None), ("GND1", G, None, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "C1.1", "R2.1"]),
                  ("n2", ["R2.2", "C2.1"]),
                  ("0", ["C1.2", "C2.2", "V1.2", "GND1.1"])])


def main():
    print("=" * 78)
    print("acmodel 纯逻辑测试：复数阻抗 + 梯形网络理论值")
    print("=" * 78)

    # ---------------------------------------------------------------- 1
    print("\n[1] 阻抗与并联")
    zc = A.impedance(irmod.Component(refdes="C1", family="CAPACITOR",
                                     part="CAPACITOR_VIRTUAL", value=C_1K), F)
    check("电容 @1kHz 的阻抗模 = 1kΩ", near(abs(zc), 1000.0, 1e-6),
          "|Z|=%.6f" % abs(zc))
    check("  纯虚且为负（容性）", near(zc.real, 0.0, 1e-9) and zc.imag < 0,
          "Z=%.3fj" % zc.imag)
    zr = A.impedance(irmod.Component(refdes="R1", family="RESISTOR",
                                     part="RESISTOR_VIRTUAL", value=1000.0), F)
    check("电阻阻抗 = 1000+0j", zr == complex(1000.0, 0.0), str(zr))
    check("不认识的元件 -> None",
          A.impedance(irmod.Component(refdes="D1", family="DIODE",
                                      part="1N4007G", value=None), F) is None)
    par = A.parallel([zr, zc])
    check("1kΩ ∥ 1kΩ∠-90° = 500-500j",
          near(par.real, 500.0) and near(par.imag, -500.0), str(par))
    check("空列表 = 开路 -> None", A.parallel([]) is None)
    check("并联含 0Ω -> 短路", A.parallel([0j, zr]) == 0j)

    # ---------------------------------------------------------------- 2
    print("\n[2] 一阶 RC（回归：v0.3.0 起就有的结论）")
    t = A.ladder_theory(ir_bypass())
    check("算得出 ac_ladder", t is not None and t["kind"] == "ac_ladder",
          str(t and t["kind"]))
    check("拓扑被判成 bypass", t and t["topology"] == "bypass",
          str(t and t["topology"]))
    check("|H| = 1/√2 = 0.70711", t and near(t["gain"], 1 / math.sqrt(2)),
          "%.6f" % (t["gain"] if t else -1))
    check("∠H = -45°", t and near(t["phase_deg"], -45.0, 1e-6),
          "%.4f°" % (t["phase_deg"] if t else 0))
    check("输入阻抗 |Z| = √2 kΩ", t and near(t["z_in"], math.sqrt(2) * 1000.0),
          "%.2f Ω" % (t["z_in"] if t else 0))

    # ---------------------------------------------------------------- 3
    print("\n[3] 并联到地：R1 串联 + (R2 ∥ C1)（v0.10.0 的新形状）")
    t = A.ladder_theory(ir_parallel())
    check("拓扑被判成 parallel_shunt",
          t and t["topology"] == "parallel_shunt", str(t and t["topology"]))
    check("1 级主干 / 2 个到地", t and (t["n_series"], t["n_shunt"]) == (1, 2),
          str(t and (t["n_series"], t["n_shunt"])))
    # Z_par = (1k · -j1k)/(1k - j1k) = 500 - j500
    # H = Z_par/(1k + Z_par) = (500-j500)/(1500-j500) = 0.44721 ∠ -26.565°
    check("|H| = 0.44721", t and near(t["gain"], 0.4472136, 1e-6),
          "%.7f" % (t["gain"] if t else -1))
    check("∠H = -26.565°", t and near(t["phase_deg"], -26.56505, 1e-4),
          "%.5f°" % (t["phase_deg"] if t else 0))
    check("逐级结果也给了", t and len(t["stages"]) == 1,
          str(t and t["stages"]))

    # 手算交叉验证：直接按复数公式算一遍，不用被测代码
    zp = (1000.0 * zc) / (1000.0 + zc)
    h = zp / (1000.0 + zp)
    check("与手算复数分压一致",
          t and near(t["gain"], abs(h), 1e-9)
          and near(t["phase_deg"], math.degrees(cmath.phase(h)), 1e-9),
          "手算 %.7f ∠ %.5f°" % (abs(h), math.degrees(cmath.phase(h))))

    # ---------------------------------------------------------------- 4
    print("\n[4] 二阶 RC 梯形：H = 1/(1-k²+3jk)，k=1 时 = 1/(3j)")
    t = A.ladder_theory(ir_ladder2())
    check("拓扑被判成 ladder", t and t["topology"] == "ladder",
          str(t and t["topology"]))
    check("|H| = 1/3 = 0.33333", t and near(t["gain"], 1.0 / 3.0, 1e-6),
          "%.7f" % (t["gain"] if t else -1))
    check("∠H = -90°", t and near(t["phase_deg"], -90.0, 1e-6),
          "%.4f°" % (t["phase_deg"] if t else 0))
    check("逐级 2 段", t and len(t["stages"]) == 2, str(t and len(t["stages"])))

    # ---------------------------------------------------------------- 5
    print("\n[5] 没有线性模型时必须返回 None（不给假数）")
    dc_only = build("dc_parallel",
                    [("V1", DC, 5.0, None), ("R1", R, 1000.0, None),
                     ("R2", R, 1000.0, None), ("GND1", G, None, None)],
                    [("in", ["V1.1", "R1.1", "R2.1"]),
                     ("0", ["R1.2", "R2.2", "V1.2", "GND1.1"])])
    check("直流源没有频率 -> None", A.ladder_theory(dc_only) is None)

    diode = build("diode",
                  [("V1", AC, 1.0, {5: F}),
                   ("D1", ("DIODE", "1N4007G"), None, None),
                   ("R1", R, 1000.0, None), ("GND1", G, None, None)],
                  [("in", ["V1.1", "D1.A"]),
                   ("n1", ["D1.K", "R1.1"]),
                   ("0", ["R1.2", "V1.2", "GND1.1"])])
    check("含二极管 -> None（二极管不是线性元件）",
          A.ladder_theory(diode) is None)

    print("\n" + "=" * 78)
    print("结果：%d 通过 / %d 失败" % (npass, nfail))
    print("=" * 78)
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
