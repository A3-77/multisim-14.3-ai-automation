# -*- coding: utf-8 -*-
"""探测：OPAMP_3T_VIRTUAL 电压跟随器能不能跑出数（v0.12.0 前置实验）。

上一版（v0.8 时代）用 LM358AD 5 端运放做同样的事，仿真返回空 channels。
这次先换最简单的 3 端虚拟运放（不需要电源脚），并把探针放在**共线折点**上
（而不是引脚上）—— 那个坑在 v0.11.0 的分叉树里已经踩过一次。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild      # noqa: E402
import ir_sim       # noqa: E402
import registry     # noqa: E402

OUT = os.path.join(ROOT, "out", "probe_opamp")
os.makedirs(OUT, exist_ok=True)


def build(family="ANALOG_VIRTUAL", part="OPAMP_3T_VIRTUAL"):
    e = registry.spec(family, part)
    donor = registry.donor_path(e)
    dref = (e.get("donor") or {}).get("refdes")
    print("donor=%s refdes=%s" % (donor, dref))

    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=1.0,
                       x=300.0, y=360.0)
    u1, _ = a.add_part(family, part, "U1", x=560.0, y=360.0,
                       donor_path=donor, donor_refdes=dref)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=700.0, y=460.0)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=560.0, y=560.0)
    pins = a.c.pin_info(u1)
    print("U1 引脚:", {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                      for k, v in pins.items()})

    a.connect([(v1, "1"), (u1, "IN+")], name="vin")
    # 反馈：OUT 连回 IN-，同时挂一个负载电阻
    n_fb = a.connect([(u1, "OUT"), (u1, "IN-"), (r1, "1")], name="fb",
                     tap=True)
    a.connect([(r1, "2"), (v1, "2"), (gnd, "1")], name="0")

    vs = a.net_vertices(n_fb)
    print("fb 网顶点:", vs)
    a.add_probe_ext(vs[1][0], vs[1][1], index=1)
    ms14 = os.path.join(OUT, "follower_3t.ms14")
    a.save(ms14)
    return ms14


def main():
    ms14 = build()
    print("文件 %s (%d 字节)" % (ms14, os.path.getsize(ms14)))
    rep = {}
    for tag, res in (
            ("dc", ir_sim.simulate_dc(ms14, verbose=True)),
            ("tran", ir_sim.simulate(ms14, stop=0.002, sample_rate=200000.0,
                                     timeout=180.0, verbose=True))):
        print("--- %s: status=%s outputs=%s"
              % (tag, res.get("status"), res.get("outputs")))
        data = res.get("data") or {}
        ch = {}
        for nm, vv in data.items():
            if not vv:
                continue
            ch[nm] = {"n": len(vv), "min": min(vv), "max": max(vv),
                      "mean": sum(vv) / len(vv)}
            print("  %-14s n=%-4d mean=%.6f min=%.6f max=%.6f"
                  % (nm, len(vv), ch[nm]["mean"], ch[nm]["min"], ch[nm]["max"]))
        rep[tag] = {"status": res.get("status"),
                    "outputs": res.get("outputs"), "channels": ch}
    with open(os.path.join(OUT, "follower_3t.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print("期望 V(out) = 1.000000 V（电压跟随器）")


if __name__ == "__main__":
    main()
