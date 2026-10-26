# -*- coding: utf-8 -*-
"""最小 DC 实验电路：5V 直流源 + 1kΩ 电阻 + 地 + 两个电压探针。

拓扑（与验收句一致）：

        V1(5V) ──┬── R1(1kΩ) ──┬── GND
                 │              │
              P1@in          P2@0

    净 in : V1.+ / R1.1   （源网 = 电阻上端，理论 5 V）
    净 0  : V1.- / GND.1 / R1.2（地，理论 0 V）
    探针  : P1@in、P2@0 —— 两个探针的差就是"电阻两端电压"

为什么两个探针都要：
    P1 读到 5V、P2 读到 0V → 电路真的在工作；
    两个都读不到        → 探针/输出注册这条路本身没通；
    只有 P1 有值        → 地网的探针没注册上（或者分析类型不对）。

本脚本**只用已验证的 add_part / connect / add_probe_ext**，
不碰任何底层生成机制。

用法：
    python tools/build_dc.py                     # 产物 out/dc/dc_min.ms14
    python tools/build_dc.py --volt 5 --ohm 1000
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

OUT = os.path.join(ROOT, "out", "dc", "dc_min.ms14")

# 坐标含义 = 引脚质心（add_part 的 anchor="pin"）
POS = {"V1": (300.0, 300.0), "R1": (500.0, 300.0), "GND": (300.0, 420.0)}


def build(volt=5.0, ohm=1000.0, out=OUT, verbose=True):
    a = msbuild.Assembler()

    v1, _ = a.add_part("POWER_SOURCES", "DC_POWER", "V1", value=volt,
                       x=POS["V1"][0], y=POS["V1"][1])
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=ohm,
                       x=POS["R1"][0], y=POS["R1"][1])
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0",
                        x=POS["GND"][0], y=POS["GND"][1])

    if verbose:
        for tag, cid in (("V1", v1), ("R1", r1), ("GND", gnd)):
            info = a.c.pin_info(cid)
            print("  %-3s 引脚: %s" % (tag, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                                            for k, v in info.items()}))

    n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
    # 地网顺序照抄 build_rc_lowpass：先垂直下到 GND，再横向到 R1，避免导线穿元件
    n_g = a.connect([(v1, "2"), (gnd, "1"), (r1, "2")], name="0")

    def pick(node_id):
        vs = a.net_vertices(node_id)
        if not vs:
            raise SystemExit("网络 %s 上没有导线顶点，探针无处可放" % node_id)
        return vs[1] if len(vs) >= 3 else vs[0]

    xy_in, xy_g = pick(n_in), pick(n_g)
    p1, _ = a.add_probe_ext(xy_in[0], xy_in[1], index=1)
    p2, _ = a.add_probe_ext(xy_g[0], xy_g[1], index=2)
    if verbose:
        print("  节点 in=%s  0=%s" % (n_in, n_g))
        print("  探针 P1@%s  P2@%s" % (xy_in, xy_g))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    n, _ = a.save(out)
    if verbose:
        print("  写出 %s (%d 字节)" % (out, n))
    return {"out": out, "bytes": n, "in": n_in, "gnd": n_g,
            "probe_xy": {"P1": xy_in, "P2": xy_g},
            "probe_local_names": [a.last_probe["local_name"]]}


def main():
    ap = argparse.ArgumentParser(description="生成最小 DC 实验电路")
    ap.add_argument("--volt", type=float, default=5.0)
    ap.add_argument("--ohm", type=float, default=1000.0)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    print("生成 DC 最小电路：%g V / %g Ω" % (args.volt, args.ohm))
    build(args.volt, args.ohm, args.out)


if __name__ == "__main__":
    main()
