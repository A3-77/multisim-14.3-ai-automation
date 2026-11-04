# -*- coding: utf-8 -*-
"""电位器方向实测：12V -> 电位器(3/2 短接) -> 10k -> 地，测中点电压。

R_eff = R(setting/100)  =>  p=10% -> 20k -> V=4.000V ; p=100% -> 200k -> V=0.571V
R_eff = R(1-setting/100)=>  p=10% ->180k -> V=0.632V ; p=100% -> 0     -> V=12.00V
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402
import ir_sim    # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1")
os.makedirs(OUT, exist_ok=True)


def build(tag, params):
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=12.0,
                       x=300.0, y=300.0)
    rw, _ = a.add_part("POTENTIOMETER", "POTENTIOMETER_VIRTUAL", "RW",
                       value=200000.0, x=500.0, y=300.0, params=params)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=700.0, y=400.0)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=700.0, y=560.0)
    print("  RW pins:", {k: (round(v["xy"][0]), round(v["xy"][1]))
                          for k, v in a.c.pin_info(rw).items()})
    a.connect([(v1, "1"), (rw, "3"), (rw, "2")], name="vcc")
    n = a.connect([(rw, "1"), (r1, "1")], name="x")
    a.connect([(r1, "2"), (v1, "2"), (gnd, "1")], name="0")
    vs = a.net_vertices(n)
    xy = vs[1] if len(vs) >= 3 else vs[0]
    a.add_probe_ext(xy[0], xy[1], index=1)
    p = os.path.join(OUT, "pot_%s.ms14" % tag)
    a.save(p)
    return p


def run(tag, params):
    print("\n--- %s params=%s" % (tag, params))
    p = build(tag, params)
    res = ir_sim.simulate(p, stop=0.01, sample_rate=200000.0,
                          timeout=90.0, verbose=False)
    data = res.get("data") or {}
    out = {}
    for nm, (tt, vv) in data.items():
        if vv:
            out[nm] = round(sum(vv[-50:]) / len(vv[-50:]), 4)
    print("  state=%s outputs=%s  V末段=%s" % (res.get("state"),
                                               res.get("outputs"), out))
    return out


if __name__ == "__main__":
    res = {}
    res["i3_10"] = run("i3_10", {3: 10.0})
    res["i7_10"] = run("i7_10", {7: 10.0})
    res["i3_100"] = run("i3_100", {3: 100.0})
    res["i7_100"] = run("i7_100", {7: 100.0})
    print("\n汇总:", json.dumps(res, ensure_ascii=False))
