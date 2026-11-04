# -*- coding: utf-8 -*-
"""决定性验证：POTENTIOMETER_VIRTUAL 的百分比能不能静态写进 .ms14。

接法：V1(12V) -> 电位器 pin1，pin2(滑动端) -> R1(1k) -> GND。
若百分比生效，R(pin1..pin2)=p*200k，则 V(1k)=12*1k/(p*200k+1k)：
    10%  -> 0.5714 V
    20%  -> 0.2308 V
    100% -> 0.0597 V
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile          # noqa: E402
import hw_lab1             # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1", "potprobe")
os.makedirs(OUT, exist_ok=True)


def build(pct, idx):
    hw_lab1.allow_parts()
    ir = irmod.CircuitIR(name="potprobe")
    C = irmod.Component

    ir.components.append(C(refdes="V1", family="POWER_SOURCES",
                           part="DC_POWER", value=12.0,
                           position=[400.0, 200.0]))
    # params: idx -> 百分比
    ir.components.append(C(refdes="RW", family="POTENTIOMETER",
                           part="POTENTIOMETER_VIRTUAL",
                           params={1: 200000.0, idx: float(pct)},
                           position=[400.0, 340.0]))
    ir.components.append(C(refdes="R1", family="RESISTOR",
                           part="RESISTOR_VIRTUAL", value=1000.0,
                           position=[400.0, 480.0]))
    ir.components.append(C(refdes="GND1", family="POWER_SOURCES",
                           part="GROUND", position=[520.0, 620.0]))

    def net(n, pins, route="hv"):
        ir.nets.append(irmod.Net(name=n, pins=pins, route=route))

    net("vcc", ["V1.1", "RW.1"])
    net("mid", ["RW.2", "R1.1"])
    net("0", ["V1.2", "R1.2", "GND1.1"], route="vh")

    ir.probes.append(irmod.Probe(refdes="P_mid", net="mid", kind="V"))
    ir.simulation.analysis = "transient"
    ir.simulation.start = 0.0
    ir.simulation.stop = 0.002
    ir.simulation.step = 1e-6
    ir.simulation.sample_rate = 1000000.0
    return ir


def run(pct, idx):
    import ir_sim
    ms14 = os.path.join(OUT, "pot_i%d_p%d.ms14" % (idx, pct))
    ir_compile.compile_ir(build(pct, idx), ms14, verbose=False)
    res = ir_sim.simulate(ms14, stop=0.002, sample_rate=1000000.0,
                          timeout=120.0, verbose=False)
    data = res.get("data") or {}
    v = None
    for nm, (_t, vv) in data.items():
        if vv:
            v = vv[-1]
            break
    return v


if __name__ == "__main__":
    for idx in (3, 5):
        print("--- 写 doubles[%d] ---" % idx)
        for pct in (10, 20, 100):
            try:
                v = run(pct, idx)
                print("   pct=%-4d V(mid) = %s" % (pct, v))
            except Exception as e:
                print("   pct=%-4d 失败 %r" % (pct, e))
