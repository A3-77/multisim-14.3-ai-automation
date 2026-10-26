# -*- coding: utf-8 -*-
"""P12：用统一入口 add_part() 生成 RC 低通滤波器。

拓扑：
    net_in : V1.1(+) --- R1.1
    net_out: R1.2     --- C1.1        ← ProbeExt 放在这条导线的拐点上
    net0   : V1.2(-) --- GND_A
    net0   : C1.2     --- GND_C

取值：V1=1V(DC)、R1=1kΩ、C1=100nF → tau = R*C = 100µs。
瞬态跑 1ms（10 个 tau），应当看到从 0 指数充电到 ≈1V。

产物：out/ref/rc_lowpass.ms14
用法：runtime\\py32\\python.exe tools\\build_rc.py [--sec 0.001]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR   # 复用已验证的 ProbeExt 克隆

OUT = os.path.join(ROOT, "out", "ref", "rc_lowpass.ms14")
DONOR_SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")

V_VOLT = 1.0
R_OHM = 1000.0
C_FARAD = 100e-9


def place(a, tag, value, pin_name, target, family, part,
          donor_path=None, donor_refdes=None):
    """在 (0,0) 克隆，然后把指定引脚平移到 target，返回 (ciid, 引脚坐标表)。

    地元件统一用位号 "0"；其余用 tag 作位号。
    """
    refdes = "0" if tag.startswith("GND") else tag
    ciid, _ = a.add_part(family, part, refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor_path, donor_refdes=donor_refdes)
    info = a.c.pin_info(ciid)
    if pin_name not in info:
        raise RuntimeError("%s 没有引脚 %r（实际 %s）" % (refdes, pin_name, list(info)))
    x0, y0 = info[pin_name]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    info = a.c.pin_info(ciid)
    print("  %-4s %-14s %-20s 引脚=%s  ← %s"
          % (tag, family, part,
             {k: (round(v["xy"][0], 1), round(v["xy"][1], 1)) for k, v in info.items()},
             os.path.basename(str(donor_path)) + "#" + str(donor_refdes)
             if donor_path is not None else "索引"))
    return ciid, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sec", type=float, default=0.001, help="瞬态时长（秒）")
    ap.add_argument("--source", choices=("index", "spice"), default="spice",
                    help="index=按 family/part 从样例索引取模板；spice=用 donor_spice.ms14")
    ap.add_argument("--out", default=None, help="输出文件名（默认 rc_lowpass.ms14）")
    ap.add_argument("--v", type=float, default=V_VOLT, help="V1 直流值（默认 1V）")
    ap.add_argument("--probe", choices=("in", "out"), default="out", help="探针放哪个网")
    args = ap.parse_args()

    # 模板来源：index 走索引解析，spice 显式指定 donor（同一套 add_part 入口）
    if args.source == "spice":
        donor = msbuild.load_donor(DONOR_SPICE)
        gnds = [c for c in donor.components() if c["part"] == "GROUND"]
        donor.set_refdes(gnds[0]["ciid"], "GNDA")
        donor.set_refdes(gnds[3]["ciid"], "GNDC")
        SRC = {
            "V1": dict(family="POWER_SOURCES", part="DC_POWER",
                       donor_path=donor, donor_refdes="V2"),
            "R1": dict(family="RESISTOR", part="RESISTOR_VIRTUAL",
                       donor_path=donor, donor_refdes="R1"),
            "C1": dict(family="CAPACITOR", part="CAPACITOR_VIRTUAL",
                       donor_path=donor, donor_refdes="C1"),
            "GNDA": dict(family="POWER_SOURCES", part="GROUND",
                         donor_path=donor, donor_refdes="GNDA"),
            "GNDC": dict(family="POWER_SOURCES", part="GROUND",
                         donor_path=donor, donor_refdes="GNDC"),
        }
    else:
        SRC = {
            "V1": dict(family="POWER_SOURCES", part="DC_POWER"),
            "R1": dict(family="RESISTOR", part="RESISTOR_VIRTUAL"),
            "C1": dict(family="CAPACITOR", part="CAPACITOR_VIRTUAL"),
            "GNDA": dict(family="POWER_SOURCES", part="GROUND"),
            "GNDC": None,      # 第二个地另找（见下）
        }

    out_path = os.path.join(ROOT, "out", "ref", args.out or "rc_lowpass.ms14")

    a = msbuild.Assembler()
    print("基底:", msbuild.BLANK, " 来源:", args.source)

    v1, vinfo = place(a, "V1", V_VOLT, "1", (300.0, 300.0), **SRC["V1"])
    r1, rinfo = place(a, "R1", R_OHM, "1", (500.0, 300.0), **SRC["R1"])
    c1, cinfo = place(a, "C1", C_FARAD, "1", (650.0, 380.0), **SRC["C1"])
    ga, gainfo = place(a, "GNDA", None, "1", (300.0, 410.0), **SRC["GNDA"])
    if SRC["GNDC"]:
        gc, gcinfo = place(a, "GNDC", None, "1", (650.0, 480.0), **SRC["GNDC"])
    else:
        # 索引分支：第二个地换个 donor，避免同一符号克隆两次
        d2 = msbuild.load_donor(DONOR_SPICE)
        g2 = [c for c in d2.components() if c["part"] == "GROUND"]
        d2.set_refdes(g2[3]["ciid"], "GNDC2")
        gc, gcinfo = place(a, "GNDC", None, "1", (650.0, 480.0),
                           family="POWER_SOURCES", part="GROUND",
                           donor_path=d2, donor_refdes="GNDC2")

    # 3) 连线
    n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
    n_out = a.connect([(r1, "2"), (c1, "1")], name="out")
    n_g1 = a.connect([(v1, "2"), (ga, "1")], name="0")
    n_g2 = a.connect([(c1, "2"), (gc, "1")], name="0")
    print("节点: in=%s out=%s gnd=%s/%s" % (n_in, n_out, n_g1, n_g2))

    # 4) 探针：放在 net_out 导线的拐点上（拐点 = C1.1 的 x、R1.2 的 y）
    px, py = cinfo["1"]["xy"][0], rinfo["2"]["xy"][1]
    elec, draw = clone_probe_ext(a, PROBE_DONOR, px, py)
    print("ProbeExt: 电气=%s 绘图=%s 位置=(%g,%g)" % (elec, draw, px, py))

    # 5) 写出 + 自检
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n, _ = a.save(out_path)
    print("写出 %s (%d 字节)" % (out_path, n))
    back = msmodel.Circuit.load(out_path)
    print("回读:", back.summary())
    for e in back.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp":
            lnk = inner[0]
            pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
            print("  wire Node=%s pts=%s" % (lnk.get("Node"), pts))
    for ref in ("V1", "R1", "C1"):
        ciid = back.find(ref)["ciid"]
        ports = {p["name"]: p["ciid"] for p in back.ports() if p["component"] == ciid}
        sym = back.symbol_of(ciid)
        bound = sum(1 for el in sym.iter() for k, v in el.attrib.items()
                    if k == "PortID" and v in ports.values())
        print("  %-3s 端口绑定 %d/%d" % (ref, bound, len(ports)))


if __name__ == "__main__":
    main()
