# -*- coding: utf-8 -*-
"""P19：用统一元件 API 生成 RC 低通，并做瞬态验证。

拓扑：
        Vin ── R1 ── Vout
                      │
                     C1
                      │
                     GND

    Vin  = AC_VOLTAGE，1 V 幅值正弦（默认 1 kHz）
    R1   = 1 kΩ
    C1   = 159 nF   →  fc = 1/(2πRC) ≈ 1001 Hz
    探针 = Vin 一个、Vout 一个（唯一命名，COM 可区分）

为什么这是第二个验收案例：
    5V 直流分压只能证明"元件导通"。RC 低通要求
    **多元件 + 多网络 + 动态仿真 + 波形符合理论**，
    输出必须是真正弦、幅值 0.707、相位 -45°，才说明整条流水线通了。

用法：
    python tools/build_rc_lowpass.py                 # 1 kHz，产物 out/ref/rc_lowpass.ms14
    python tools/build_rc_lowpass.py --freq 10000 --out out/rc_10k.ms14
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

# 布局。坐标含义 = **元件引脚质心**（add_part 的 anchor="pin"），不是符号锚点。
# 选这组位置是为了让导线不跨接：R1/C1 都在 V1 右侧，地线从 V1.2 垂直下来
# 再横向右行，不会穿过任何别的网络。
POS = {
    "V1": (300.0, 300.0),
    "GND": (300.0, 420.0),
    "R1": (500.0, 300.0),
    "C1": (700.0, 400.0),
}


def build(freq=1000.0, amp=1.0, r=1000.0, c=159e-9, out=None):
    a = msbuild.Assembler()

    v1, _ = a.add_part("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                       value=amp, x=POS["V1"][0], y=POS["V1"][1],
                       params={5: freq})
    r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1",
                       value=r, x=POS["R1"][0], y=POS["R1"][1])
    c1, _ = a.add_part("CAPACITOR", "CAPACITOR_VIRTUAL", "C1",
                       value=c, x=POS["C1"][0], y=POS["C1"][1])
    gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0",
                        x=POS["GND"][0], y=POS["GND"][1])

    for tag, cid in (("V1", v1), ("R1", r1), ("C1", c1), ("GND", gnd)):
        info = a.c.pin_info(cid)
        print("  %-4s 引脚: %s" % (tag, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                                        for k, v in info.items()}))

    # 网络。地网的引脚顺序特意排成 V1.2 → GND → C1.2：
    # connect() 按顺序把相邻引脚用导线串起来，这样地线先垂直下到 GND，
    # 再横向右行到 C1，不会从 R1/C1 本体中间穿过去。
    n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
    n_out = a.connect([(r1, "2"), (c1, "1")], name="out")
    n_gnd = a.connect([(v1, "2"), (gnd, "1"), (c1, "2")], name="0")
    print("  节点: in=%s out=%s gnd=%s" % (n_in, n_out, n_gnd))

    # 探针：落在各自网络的导线顶点上（不能落线段中间）
    def pick(node_id, prefer_bend=True):
        vs = a.net_vertices(node_id)
        if not vs:
            raise SystemExit("网络 %s 上没有导线顶点" % node_id)
        return vs[1] if (prefer_bend and len(vs) >= 3) else vs[0]

    xy_in = pick(n_in)
    xy_out = pick(n_out)
    p1, _ = a.add_probe_ext(xy_in[0], xy_in[1])
    p2, _ = a.add_probe_ext(xy_out[0], xy_out[1])
    print("  探针: Vin@%s -> %s / Vout@%s -> %s"
          % (xy_in, p1, xy_out, p2))

    out = out or os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n, _ = a.save(out)
    print("写出 %s (%d 字节)" % (out, n))

    # 回读自检：网络成员 + 探针名
    back = __import__("msmodel").Circuit.load(out)
    pm = {p["ciid"]: p for p in back.ports()}
    refs = {x["ciid"]: x["refdes"] for x in back.components()}
    for nd in back.nodes():
        names = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                names.append("%s.%s" % (refs.get(p["component"], "?"), p["name"]))
        if names:
            print("  net %-6s %s" % (nd.get("name"), names))
    probes = [(e.get("CiID"), e.find("CiProbeExtComp").get("LocalName"))
              for e in back.elements if e.get("Class") == "CiProbeExtComp"]
    print("  探针:", probes)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", type=float, default=1000.0, help="正弦频率 Hz")
    ap.add_argument("--amp", type=float, default=1.0, help="正弦幅值 V")
    ap.add_argument("--r", type=float, default=1000.0, help="R1 阻值 Ω")
    ap.add_argument("--c", type=float, default=159e-9, help="C1 容值 F")
    ap.add_argument("--out", default=None, help="输出路径")
    args = ap.parse_args()
    build(args.freq, args.amp, args.r, args.c, args.out)


if __name__ == "__main__":
    main()
