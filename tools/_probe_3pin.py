# -*- coding: utf-8 -*-
"""三端/五端器件端到端实验：NPN 二极管接法 + 运放电压跟随器。"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild      # noqa: E402
import ir_sim       # noqa: E402

OUT = os.path.join(ROOT, "out", "probe_parts")
os.makedirs(OUT, exist_ok=True)
REPORT = {}


def run(name, builder, stop, expect):
    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)
    try:
        ms14, meta = builder()
        print("  结构: %s" % json.dumps(meta, ensure_ascii=False))
        print("  文件: %s (%d bytes)" % (ms14, os.path.getsize(ms14)))
        c2 = msbuild.load_donor(ms14)
        print("  回读: " + " | ".join(
            "%s=%s/%s%s" % (d["refdes"], d["family"], d["part"], list(c2.pin_info(d["ciid"])))
            for d in c2.components()))
        res = ir_sim.simulate(ms14, stop=stop, sample_rate=200000.0, timeout=180.0, verbose=False)
        data = res.get("data") or {}
        print("  sim: status=%s outputs=%s" % (res.get("status"), res.get("outputs")))
        got = {}
        for nm, (tt, vv) in data.items():
            if not vv:
                continue
            got[nm] = {"n": len(vv), "min": min(vv), "max": max(vv),
                       "mean": sum(vv) / len(vv), "last": vv[-1]}
            print("    %-14s n=%-6d min=%8.4f max=%8.4f mean=%8.4f last=%8.4f"
                  % (nm, len(vv), min(vv), max(vv), sum(vv) / len(vv), vv[-1]))
        REPORT[name] = {"ok": bool(got), "meta": meta, "channels": got, "expect": expect}
    except Exception as e:
        print("  !! 失败: %s" % e)
        traceback.print_exc()
        REPORT[name] = {"ok": False, "error": str(e)}


# ----------------------------------------------------------------------
def build_npn():
    """NPN 二极管接法：B 与 C 短接到同一节点，经 R 接 5V，E 接地。
    预期 V(节点) ≈ Vbe ≈ 0.65–0.80 V。"""
    a = msbuild.Assembler()
    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=5.0, x=300.0, y=300.0)
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0, x=500.0, y=300.0)
    q1, _ = a.add_part("BJT_NPN", "2N2222A", "Q1", x=700.0, y=300.0)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=700.0, y=440.0)
    pins = a.c.pin_info(q1)
    print("  Q1 引脚:", {k: (round(v["xy"][0], 1), round(v["xy"][1], 1)) for k, v in pins.items()})

    n_v = a.connect([(v1, "1"), (r1, "1")], name="vcc")
    n_x = a.connect([(r1, "2"), (q1, "B"), (q1, "C")], name="x")
    a.connect([(v1, "2"), (q1, "E"), (gnd, "1")], name="0")

    vs = a.net_vertices(n_x)
    xy = vs[1] if len(vs) >= 3 else vs[0]
    a.add_probe_ext(xy[0], xy[1], index=1)
    ms14 = os.path.join(OUT, "npn_diode_connected.ms14")
    a.save(ms14)
    return ms14, {"Q1_pins": sorted(pins), "probe": "V(节点 x)"}


def build_opamp():
    """运放电压跟随器：IN+ 接 1V 直流，OUT 接回 IN-，读 OUT。
    预期 OUT ≈ 1.0 V。"""
    a = msbuild.Assembler()
    vin, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=1.0, x=260.0, y=360.0)
    vp, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V2", value=15.0, x=260.0, y=180.0)
    vn, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V3", value=-15.0, x=260.0, y=540.0)
    u1, _ = a.add_part("OPAMP", "LM358AD", "U1", x=560.0, y=360.0)
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=560.0, y=620.0)
    pins = a.c.pin_info(u1)
    print("  U1 引脚:", {k: (round(v["xy"][0], 1), round(v["xy"][1], 1)) for k, v in pins.items()})

    a.connect([(vin, "1"), (u1, "1IN+")], name="vin")
    n_fb = a.connect([(u1, "1OUT"), (u1, "1IN-")], name="fb")
    a.connect([(vp, "1"), (u1, "VS+")], name="vp")
    a.connect([(vn, "1"), (u1, "VS-")], name="vn")
    a.connect([(vin, "2"), (vp, "2"), (vn, "2"), (gnd, "1")], name="0")

    vs = a.net_vertices(n_fb)
    print("  反馈网顶点: %s" % (vs,))
    xy = vs[1] if len(vs) >= 3 else vs[0]
    a.add_probe_ext(xy[0], xy[1], index=1)
    ms14 = os.path.join(OUT, "opamp_follower.ms14")
    a.save(ms14)
    return ms14, {"U1_pins": sorted(pins), "probe": "V(1OUT) @ %s" % (xy,)}


run("NPN 2N2222A 二极管接法", build_npn, 0.002, "V(x) ≈ 0.65–0.80 V")
run("OPAMP LM358AD 电压跟随器", build_opamp, 0.002, "V(out) ≈ 1.0 V")

with open(os.path.join(OUT, "transistor_opamp.json"), "w", encoding="utf-8") as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print("\n完成。")
