# -*- coding: utf-8 -*-
"""对照实验：普通电阻分压 vs 电位器分压，看探针能否注册。"""
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


def probe_at(a, node, tag=""):
    vs = a.net_vertices(node)
    print("  net %s vertices=%s" % (tag, vs))
    if not vs:
        return None
    xy = vs[1] if len(vs) >= 3 else vs[0]
    a.add_probe_ext(xy[0], xy[1], index=1)
    print("  probe at", xy)
    return xy


def build_rr():
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=12.0,
                       x=300.0, y=300.0)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=500.0, y=250.0)
    r2, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R2", value=10000.0,
                       x=500.0, y=400.0)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=500.0, y=560.0)
    a.connect([(v1, "1"), (r1, "1")], name="vcc")
    n = a.connect([(r1, "2"), (r2, "1")], name="mid")
    a.connect([(r2, "2"), (v1, "2"), (gnd, "1")], name="0")
    probe_at(a, n, "mid")
    p = os.path.join(OUT, "ctl_rr.ms14")
    a.save(p)
    return p


def build_pot():
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=12.0,
                       x=300.0, y=300.0)
    rw, _ = a.add_part("POTENTIOMETER", "POTENTIOMETER_VIRTUAL", "RW",
                       value=200000.0, x=500.0, y=300.0, params={3: 10.0})
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=700.0, y=400.0)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=700.0, y=560.0)
    a.connect([(v1, "1"), (rw, "3"), (rw, "2")], name="vcc")
    n = a.connect([(rw, "1"), (r1, "1")], name="x")
    a.connect([(r1, "2"), (v1, "2"), (gnd, "1")], name="0")
    probe_at(a, n, "x")
    p = os.path.join(OUT, "ctl_pot.ms14")
    a.save(p)
    return p


def run(tag, builder):
    print("\n=== %s" % tag)
    p = builder()
    res = ir_sim.simulate(p, stop=0.01, sample_rate=200000.0, timeout=90.0,
                          verbose=True)
    data = res.get("data") or {}
    out = {nm: round(sum(vv[-30:]) / len(vv[-30:]), 4)
           for nm, (tt, vv) in data.items() if vv}
    print("  -> %s  %s" % (res.get("state"), out))
    return out


if __name__ == "__main__":
    r = {}
    r["rr"] = run("电阻分压（对照）", build_rr)
    r["pot"] = run("电位器分压", build_pot)
    print("\n汇总:", json.dumps(r, ensure_ascii=False))
