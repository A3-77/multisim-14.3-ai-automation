# -*- coding: utf-8 -*-
"""P13：分压器三变体，判定「电阻不导通」还是「探针绑错网」。

  --probe src|mid  探针放源网顶点 / 中点顶点
  --r2 yes|no      是否保留 R2（no = 只留 V1-R1-中点-C-GND）
  --cap F          跨接电容容值（默认 1pF，太小的话仿真会秒停）

用法：
  python tools/p13_build.py --probe src --r2 yes --out p13_a1.ms14
  python tools/p13_build.py --probe mid --r2 yes --out p13_a2.ms14
  python tools/p13_build.py --probe mid --r2 no  --out p13_a3.ms14
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")


def place(a, refdes, target, pin="1", donor=None, donor_ref=None, value=None):
    ciid, _ = a.add_part("X", "Y", refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor, donor_refdes=donor_ref)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    return ciid, a.c.pin_info(ciid)


def attach(a, ciid, pin, node_id):
    """把元件的某个引脚挂到已存在的 CiNode 上（不新建节点）。"""
    p = next(x for x in a.c.ports() if x["component"] == ciid and x["name"] == pin)
    nd = p["port"].find("Nodes")
    if nd is None:
        nd = ET.SubElement(p["port"], "Nodes")
    it = ET.SubElement(nd, "Item")
    it.set("CiID", node_id)
    for e in a.c.elements:
        if e.get("CiID") == node_id:
            ref = ET.SubElement(e.find("CiNode/Ports"), "Item")
            ref.set("CiID", p["ciid"])
            return
    raise KeyError(node_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", choices=("src", "mid"), default="mid")
    ap.add_argument("--r2", choices=("yes", "no"), default="yes")
    ap.add_argument("--cap", type=float, default=1e-12)
    ap.add_argument("--out", default="p13_build.ms14")
    args = ap.parse_args()

    a = msbuild.Assembler()
    d = msbuild.load_donor(SPICE)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[3]["ciid"], "GNDC")

    v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref="V2", value=5.0)
    r1, rinfo = place(a, "R1", (500.0, 340.0), donor=d, donor_ref="R1", value=1000.0)
    print("  V1", {k: v["xy"] for k, v in vinfo.items()})
    print("  R1", {k: v["xy"] for k, v in rinfo.items()})

    n_in = a.connect([(v1, "1"), (r1, "1")], name="1")
    n_mid = a.connect([(r1, "2")], name="2")
    print("  节点 in=%s mid=%s" % (n_in, n_mid))

    # 中点网的下一级：有 R2 就是 R2，没有就让 C1 顶上去（保证中点网有导线、有顶点）
    mid_xy = (650.0, rinfo["2"]["xy"][1])
    if args.r2 == "yes":
        r2, r2info = place(a, "R2", (650.0, 430.0), donor=d, donor_ref="R1", value=1000.0)
        print("  R2", {k: v["xy"] for k, v in r2info.items()})
        attach(a, r2, "1", n_mid)
        a.wire(n_mid, (r1, "2"), (r2, "1"))
        nxt = (r2, "1")
        c1_xy = (790.0, 430.0)
    else:
        c1_xy = (650.0, 430.0)
        nxt = None

    # 中点跨接电容（保证仿真有动态过程，否则纯电阻会秒停）
    c1, cinfo = place(a, "C1", c1_xy, donor=d, donor_ref="C1", value=args.cap)
    print("  C1", {k: v["xy"] for k, v in cinfo.items()})
    attach(a, c1, "1", n_mid)
    if nxt is None:
        a.wire(n_mid, (r1, "2"), (c1, "1"))
    gc2, _ = place(a, "0", (c1_xy[0], c1_xy[1] + 90.0), donor=d, donor_ref="GNDC")
    a.connect([(c1, "2"), (gc2, "1")], name="0")

    if args.r2 == "yes":
        gc, ginfo = place(a, "0", (650.0, 520.0), donor=d, donor_ref="GNDC")
        a.connect([(r2, "2"), (gc, "1")], name="0")

    ga, _ = place(a, "0", (300.0, 430.0), donor=d, donor_ref="GNDA")
    a.connect([(v1, "2"), (ga, "1")], name="0")

    probe_xy = (500.0, 300.0) if args.probe == "src" else mid_xy
    clone_probe_ext(a, PROBE_DONOR, *probe_xy)
    print("  探针 %s @ %s" % (args.probe, probe_xy))

    out = os.path.join(ROOT, "out", args.out)
    n, _ = a.save(out)
    print("写出 %s (%d 字节)" % (out, n))
    back = msmodel.Circuit.load(out)
    pm = {p["ciid"]: p for p in back.ports()}
    for nd in back.nodes():
        names = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                ref = next((x["refdes"] for x in back.components() if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        print("  node %-10s name=%-3r ports=%s" % (nd["ciid"], nd["name"], names))
    for e in back.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp":
            print("  wire Node=%s pts=%s" % (inner[0].get("Node"),
                  [(p.get("X"), p.get("Y")) for p in inner[0].find("Points")]))


if __name__ == "__main__":
    main()
