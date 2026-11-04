# -*- coding: utf-8 -*-
"""诊断：运放为什么仿真不出数。四种配置逐个试，打印失败原因。"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild      # noqa: E402
import ir_sim       # noqa: E402
import registry     # noqa: E402

OUT = os.path.join(ROOT, "out", "probe_opamp")
os.makedirs(OUT, exist_ok=True)
REP = {}


def donor_of(family, part):
    e = registry.spec(family, part)
    return registry.donor_path(e), (e.get("donor") or {}).get("refdes")


def build_3t_follower():
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=1.0,
                       x=300.0, y=360.0)
    d, dr = donor_of("ANALOG_VIRTUAL", "OPAMP_3T_VIRTUAL")
    u1, _ = a.add_part("ANALOG_VIRTUAL", "OPAMP_3T_VIRTUAL", "U1",
                       x=560.0, y=360.0, donor_path=d, donor_refdes=dr)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=700.0, y=460.0)
    g, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=560.0, y=560.0)
    a.connect([(v1, "1"), (u1, "IN+")], name="vin")
    n = a.connect([(u1, "OUT"), (u1, "IN-"), (r1, "1")], name="fb", tap=True)
    a.connect([(r1, "2"), (v1, "2"), (g, "1")], name="0")
    a.add_probe_ext(*a.net_vertices(n)[1], index=1)
    return a, os.path.join(OUT, "d1_3t_follower.ms14")


def build_3t_open():
    """开环：IN- 接地，OUT 只接负载。理想运放会饱和，但至少能跑。"""
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=1.0,
                       x=300.0, y=360.0)
    d, dr = donor_of("ANALOG_VIRTUAL", "OPAMP_3T_VIRTUAL")
    u1, _ = a.add_part("ANALOG_VIRTUAL", "OPAMP_3T_VIRTUAL", "U1",
                       x=560.0, y=360.0, donor_path=d, donor_refdes=dr)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=700.0, y=360.0)
    g, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=560.0, y=560.0)
    a.connect([(v1, "1"), (u1, "IN+")], name="vin")
    n = a.connect([(u1, "OUT"), (r1, "1")], name="out")
    a.connect([(u1, "IN-"), (r1, "2"), (v1, "2"), (g, "1")], name="0")
    a.add_probe_ext(*a.net_vertices(n)[1], index=1)
    return a, os.path.join(OUT, "d2_3t_open.ms14")


def build_5t(family, part, tag):
    """5 端运放 + 双电源，电压跟随器。"""
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=1.0,
                       x=300.0, y=460.0)
    vp, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V2", value=15.0,
                       x=300.0, y=200.0)
    vn, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V3", value=-15.0,
                       x=300.0, y=700.0)
    d, dr = donor_of(family, part)
    u1, _ = a.add_part(family, part, "U1", x=600.0, y=460.0,
                       donor_path=d, donor_refdes=dr)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0,
                       x=760.0, y=560.0)
    g, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=600.0, y=800.0)
    pins = a.c.pin_info(u1)
    print("   %s 引脚: %s" % (tag, sorted(pins)))
    ip = "IN+" if "IN+" in pins else "1IN+"
    im = "IN-" if "IN-" in pins else "1IN-"
    op = "OUT" if "OUT" in pins else "1OUT"
    a.connect([(v1, "1"), (u1, ip)], name="vin")
    n = a.connect([(u1, op), (u1, im), (r1, "1")], name="fb", tap=True)
    a.connect([(vp, "1"), (u1, "VS+")], name="vp")
    a.connect([(vn, "1"), (u1, "VS-")], name="vn")
    a.connect([(r1, "2"), (v1, "2"), (vp, "2"), (vn, "2"), (g, "1")], name="0")
    a.add_probe_ext(*a.net_vertices(n)[1], index=1)
    return a, os.path.join(OUT, "d3_%s_follower.ms14" % tag)


def run(name, builder):
    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)
    try:
        a, path = builder()
        a.save(path)
        print("   文件 %d 字节" % os.path.getsize(path))
        res = ir_sim.simulate_dc(path, verbose=True)
        outs = res.get("outputs") or []
        data = res.get("data") or {}
        print("   status=%s outputs=%s" % (res.get("status"), outs))
        ch = {}
        for nm, vv in data.items():
            if vv:
                ch[nm] = {"mean": sum(vv) / len(vv), "n": len(vv)}
                print("   %-14s mean=%.6f n=%d" % (nm, ch[nm]["mean"], len(vv)))
        REP[name] = {"ok": bool(ch), "outputs": outs,
                     "status": res.get("status"), "channels": ch,
                     "file": os.path.relpath(path, ROOT)}
    except Exception as e:
        print("   !! %s" % e)
        traceback.print_exc()
        REP[name] = {"ok": False, "error": str(e)}


run("1 · 3T 虚拟运放 · 跟随器", build_3t_follower)
run("2 · 3T 虚拟运放 · 开环", build_3t_open)
run("3 · 5T 虚拟运放 · 跟随器(±15V)",
    lambda: build_5t("ANALOG_VIRTUAL", "OPAMP_5T_VIRTUAL", "5t"))
run("4 · LM358AD · 跟随器(±15V)",
    lambda: build_5t("OPAMP", "LM358AD", "lm358"))

with open(os.path.join(OUT, "diagnose.json"), "w", encoding="utf-8") as f:
    json.dump(REP, f, ensure_ascii=False, indent=2)
print("\n报告: out/probe_opamp/diagnose.json")
