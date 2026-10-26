# -*- coding: utf-8 -*-
"""P15 判定：把源电压改成 3V，探针在源网。

若读 3V -> 仿真真的在算（读数随源变），那中点 0V 就是电路问题
若仍读 5V / 0V -> 说明读到的是静态填充值，整条读取链路不可信

用法：python tools/p15_v3.py
产物：out/p15_v3.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")
OUT = os.path.join(ROOT, "out", "p15_v3.ms14")


def place(a, refdes, target, pin="1", donor=None, donor_ref=None, value=None):
    ciid, _ = a.add_part("X", "Y", refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor, donor_refdes=donor_ref)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    return ciid, a.c.pin_info(ciid)


def main():
    a = msbuild.Assembler()
    d = msbuild.load_donor(SPICE)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[3]["ciid"], "GNDC")

    # 只放 V1(3V) + R1 + C1，探针在源网（V1.1/R1.1 之间）
    v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref="V2", value=3.0)
    r1, rinfo = place(a, "R1", (500.0, 340.0), donor=d, donor_ref="R1", value=1000.0)
    c1, cinfo = place(a, "C1", (650.0, 340.0), donor=d, donor_ref="C1", value=1e-7)

    n_src = a.connect([(v1, "1"), (r1, "1"), (c1, "1")], name="1")
    n_out = a.connect([(r1, "2"), (c1, "2")], name="2")
    ga, _ = place(a, "0", (300.0, 430.0), donor=d, donor_ref="GNDA")
    a.connect([(v1, "2"), (ga, "1")], name="0")
    g2, _ = place(a, "0", (650.0, 460.0), donor=d, donor_ref="GNDC")
    a.connect([(c1, "2"), (g2, "1")], name="0")

    # 探针放在源网导线拐点
    px, py = 500.0, 300.0
    clone_probe_ext(a, PROBE_DONOR, px, py)
    print("V1=3V，探针在源网 (%g,%g)，R1=1k，C1=100nF" % (px, py))

    n, _ = a.save(OUT)
    print("写出 %s (%d 字节)" % (OUT, n))
    back = msmodel.Circuit.load(OUT)
    print("V1 参数:", back.params(back.find("V1")["comp"])[:3])
    pm = {p["ciid"]: p for p in back.ports()}
    for nd in back.nodes():
        names = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                ref = next((x["refdes"] for x in back.components()
                            if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        print("  node %-10s name=%-3r %s" % (nd["ciid"], nd["name"], names))


if __name__ == "__main__":
    main()
