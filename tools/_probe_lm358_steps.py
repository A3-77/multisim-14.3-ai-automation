# -*- coding: utf-8 -*-
"""LM358 最小电路阶梯测试：从全接地开始，一项一项加，找出哪一步开始失败。"""
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
REP = {}

DONOR, DREF = None, None
_e = registry.spec("OPAMP", "LM358AD")
DONOR = registry.donor_path(_e)
DREF = (_e.get("donor") or {}).get("refdes")


def make(tag, supply="single", sig=0.0, feedback=False):
    a = msbuild.Assembler()
    u1, _ = a.add_part("OPAMP", "LM358AD", "U1", x=600.0, y=400.0,
                       donor_path=DONOR, donor_refdes=DREF)
    rl, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "RL", value=10000.0,
                       x=760.0, y=500.0)
    g, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=600.0, y=760.0)

    if supply == "single":
        vp, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V2", value=5.0,
                           x=400.0, y=200.0)
        a.connect([(vp, "1"), (u1, "VS+")], name="vp")
        a.connect([(u1, "VS-"), (vp, "2")], name="vn")
        rail_neg = "vn"
    else:
        vp, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V2", value=15.0,
                           x=400.0, y=200.0)
        vn, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V3", value=-15.0,
                           x=400.0, y=650.0)
        a.connect([(vp, "1"), (u1, "VS+")], name="vp")
        a.connect([(vn, "1"), (u1, "VS-")], name="vn")
        rail_neg = "0"

    # 输入
    if sig:
        v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=sig,
                           x=300.0, y=350.0)
        a.connect([(v1, "1"), (u1, "IN+" if "IN+" in
                               a.c.pin_info(u1) else "1IN+")], name="vin")
        a.connect([(v1, "2"), (g, "1")], name="0")
        if supply != "single":
            a.connect([(vp, "2"), (vn, "2"), (g, "1")], name="0")
        else:
            a.connect([(vp, "2"), (g, "1")], name="0")
        vin_neg = "0"
    else:
        a.connect([(u1, "1IN+"), (g, "1")], name="0")
        if supply == "single":
            a.connect([(vp, "2"), (g, "1")], name="0")
        else:
            a.connect([(vp, "2"), (vn, "2"), (g, "1")], name="0")
        vin_neg = "0"

    # 输出负载
    n_out = a.connect([(u1, "1OUT"), (rl, "1")], name="out")
    a.connect([(rl, "2"), (g, "1")], name="0")

    # 反馈
    if feedback:
        a.connect([(u1, "1OUT"), (u1, "1IN-")], name="fb", tap=True)
    else:
        a.connect([(u1, "1IN-"), (g, "1")], name="0")

    vs = a.net_vertices(n_out)
    print("   out 顶点:", vs)
    a.add_probe_ext(vs[1][0], vs[1][1], index=1)
    path = os.path.join(OUT, "step_%s.ms14" % tag)
    a.save(path)
    return path


def run(tag, **kw):
    print("\n" + "=" * 70)
    print(tag)
    print("=" * 70)
    try:
        path = make(tag, **kw)
        res = ir_sim.simulate_dc(path, verbose=True)
        outs = res.get("outputs") or []
        data = res.get("data") or {}
        ch = {}
        for nm, vv in data.items():
            if vv:
                ch[nm] = {"mean": sum(vv) / len(vv), "n": len(vv)}
                print("   %-14s mean=%.6f" % (nm, ch[nm]["mean"]))
        REP[tag] = {"ok": bool(ch), "outputs": outs, "channels": ch,
                    "file": os.path.relpath(path, ROOT)}
    except Exception as e:
        print("   !! %r" % (e,))
        REP[tag] = {"ok": False, "error": str(e)}


run("a_single_allzero", supply="single", sig=0.0, feedback=False)
run("b_single_sig", supply="single", sig=1.0, feedback=False)
run("c_single_follower", supply="single", sig=1.0, feedback=True)
run("d_dual_follower", supply="dual", sig=1.0, feedback=True)

with open(os.path.join(OUT, "steps.json"), "w", encoding="utf-8") as f:
    json.dump(REP, f, ensure_ascii=False, indent=2)
print("\n汇总：")
for k, v in REP.items():
    print("  %-22s ok=%-5s %s" % (k, v["ok"],
                                  {n: round(c["mean"], 4)
                                   for n, c in (v.get("channels") or {}).items()}))
