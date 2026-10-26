# -*- coding: utf-8 -*-
"""P18: 最小导通测试 —— 只有 V1 和 R1，探针挂在 R1 另一端，用 dc_op 读解。

A: V1(5V) node1-0 ; R1(1k) node1-node2 ; 探针 node2 ; node2 上没别的元件
   → R1 若导通，node2 无负载 → dc_op 应给 5V

B: V1(5V) node1-0 ; 探针 node1（源网，基准）; R1 node1-node0
   → 应给 5V（对照，已知源网正常）

C: 同 A，但 R1 换成 1µΩ（近似短路）
   → 若 A 给 0、C 也给 0，说明 R1 根本不在网表里，跟阻值无关

用法: runtime\py32\python.exe tools\p18_min.py
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


def build(tag, mode):
    a = msbuild.Assembler()
    d = msbuild.load_donor(SPICE)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[3]["ciid"], "GNDC")

    v1, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
    a.c.set_value_by_refdes("V1", 5.0)
    r1, _ = a.add(msbuild.Donor(d, "R1"), x=520.0, y=340.0, refdes="R1")
    a.c.set_value_by_refdes("R1", 1e-6 if mode == "short" else 1000.0)
    g1, _ = a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=520.0, refdes="0")

    if mode == "probe_src":
        n = a.connect([(v1, "1"), (r1, "1")], name="1")
        a.connect([(r1, "2"), (g1, "1")], name="0")
        a.connect([(v1, "2"), (g1, "1")], name="0")
    else:
        # V1.1 - R1.1 ; R1.2 悬空(只有探针) ; V1.2 - GND
        n = a.connect([(r1, "2")], name="2")
        a.connect([(v1, "1"), (r1, "1")], name="1")
        a.connect([(v1, "2"), (g1, "1")], name="0")

    vx = None
    for e in a.objs:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == n:
            pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
            vx = pts[0]
            print("[%s] 探针网 %s pts=%s 落点=%s" % (tag, n, pts, vx))
            break
    if vx is None:
        # 没有导线：探针直接放在引脚坐标上
        info = a.c.pin_info(r1)
        vx = info["2"]["xy"]
        print("[%s] 无导线，探针放 R1.2 引脚 %s" % (tag, vx))
    clone_probe_ext(a, PROBE_DONOR, vx[0], vx[1])

    out = os.path.join(ROOT, "out", "p18_min_%s.ms14" % tag)
    nbytes, _ = a.save(out)
    print("[%s] 写出 %s (%d 字节)" % (tag, out, nbytes))
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


if __name__ == "__main__":
    build("a", "open")
    build("b", "probe_src")
    build("c", "short")
