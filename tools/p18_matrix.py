# -*- coding: utf-8 -*-
"""P18 矩阵：三个极小电路，分离「探针绑定」与「元件导通」两件事。

所有网络都只有 2 个引脚（不需要 junction），排除交汇因素。

T1  V1(5V) - R1(1k) - C1(1µF) - GND      探针在 R1/C1 之间 → 期望稳在 5V
T2  V1(5V) - C1(1µF) - R1(1k) - GND      探针在 C1/R1 之间 → 期望 5V 指数衰减到 0
T3  V1(5V) - C1(1µF) - GND               探针在 V1/C1 之间（源网）→ 期望稳在 5V

判读：
  T1=5V          → R 导通、C 不短路
  T2 有 5V→0 衰减 → C 导通、R 导通、探针在非源网也能正常绑定
  T2 恒 0        → 要么 C 开路，要么探针绑定到地
  T3=5V          → 源网正常（已知）
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
OUTDIR = os.path.join(ROOT, "out")


def build(tag, order):
    """order: 'RC' 或 'CR' 或 'C'"""
    a = msbuild.Assembler()
    d = msbuild.load_donor(SPICE)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    d.set_refdes(gnds[0]["ciid"], "GNDA")

    v1, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
    a.c.set_value_by_refdes("V1", 5.0)

    g1, _ = a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=560.0, refdes="0")

    # 串联元件，x 递增
    chain = []
    x = 480.0
    for kind in order:
        if kind == "R":
            cid, _ = a.add(msbuild.Donor(d, "R1"), x=x, y=340.0, refdes="R1")
            a.c.set_value_by_refdes("R1", 1000.0)
        else:
            cid, _ = a.add(msbuild.Donor(d, "C1"), x=x, y=340.0, refdes="C1")
            a.c.set_value_by_refdes("C1", 1e-6)
        chain.append(cid)
        x += 160.0

    # V1.1 -> chain[0].1 -> chain[0].2 -> chain[1].1 -> ... -> chain[-1].2 -> GND
    n_first = a.connect([(v1, "1"), (chain[0], "1")], name="1")
    probe_node = n_first
    for i in range(len(chain) - 1):
        nn = a.connect([(chain[i], "2"), (chain[i + 1], "1")], name=str(2 + i))
        if i == 0:
            probe_node = nn
    a.connect([(chain[-1], "2"), (g1, "1")], name="0")
    a.connect([(v1, "2"), (g1, "1")], name="0")

    # 探针放在 probe_node 的拐点
    vx = None
    for e in a.objs:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == probe_node:
            pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
            vx = pts[1] if len(pts) >= 3 else pts[0]
            print("[%s] 探针网 %s 导线 pts=%s 落点=%s" % (tag, probe_node, pts, vx))
            break
    if vx is None:
        raise SystemExit("[%s] 找不到探针网导线" % tag)
    clone_probe_ext(a, PROBE_DONOR, vx[0], vx[1])

    out = os.path.join(OUTDIR, "p18_%s.ms14" % tag)
    n, _ = a.save(out)
    print("[%s] 写出 %s (%d 字节)" % (tag, out, n))
    back = msmodel.Circuit.load(out)
    pm = {p["ciid"]: p for p in back.ports()}
    for nd in back.nodes():
        names = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                ref = next((x["refdes"] for x in back.components()
                            if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        print("     node %-10s ports=%s" % (nd["ciid"], names))
    return out


if __name__ == "__main__":
    build("t1", "RC")
    build("t2", "CR")
    build("t3", "C")
