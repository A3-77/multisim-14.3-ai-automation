# -*- coding: utf-8 -*-
"""P17: 一刀切开 —— 同一电路，探针分别落在「源网」和「中点网」，出两个文件。

目的：p15_divider 中点恒为 0V。两种可能：
  (a) V1 根本没驱动（源网也是 0V）→ 问题在电源/网络层
  (b) 源网 5V、中点 0V → 问题在电阻（开路/引脚未绑定）

之所以拆成两个文件而不是一个文件放两个探针：两个 ProbeExt 克隆出来会拿到
**同名输出** V(探针2)，COM 读取直接报「未指定的错误」（p17 实测）。

布局：V1(5V, 300,300) -- R1(1k, 500,340) -- 中点 -- R2(1k, 650,430) -- GND
      C1(1pF) 跨中点-地，保证瞬态持续 running

用法: runtime\py32\python.exe tools\p17_split.py
产物: out/p17_in.ms14   （探针在源网导线拐点 493,300）
      out/p17_mid.ms14  （探针在中点导线拐点 643,381）
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


def wire_pts(a, node):
    for e in a.objs:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == node:
            return e.get("ID"), [(float(p.get("X")), float(p.get("Y")))
                                 for p in inner[0].find("Points")]
    return None, None


def pick_vertex(pts):
    """取中间顶点（非首尾 = 不是引脚端点）。"""
    return pts[1] if len(pts) >= 3 else None


def build(where):
    a = msbuild.Assembler()
    d = msbuild.load_donor(SPICE)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[3]["ciid"], "GNDC")

    v1, _ = a.add(msbuild.Donor(d, "V2"), x=300.0, y=300.0, refdes="V1")
    a.c.set_value_by_refdes("V1", 5.0)
    r1, _ = a.add(msbuild.Donor(d, "R1"), x=500.0, y=340.0, refdes="R1")
    a.c.set_value_by_refdes("R1", 1000.0)
    r2, _ = a.add(msbuild.Donor(d, "R1"), x=650.0, y=430.0, refdes="R2")
    a.c.set_value_by_refdes("R2", 1000.0)
    c1, _ = a.add(msbuild.Donor(d, "C1"), x=790.0, y=430.0, refdes="C1")
    a.c.set_value_by_refdes("C1", 1e-12)

    n_in = a.connect([(v1, "1"), (r1, "1")], name="1")
    n_mid = a.connect([(r1, "2"), (r2, "1"), (c1, "1")], name="2")
    a.connect([(v1, "2"), (a.add(msbuild.Donor(d, "GNDA"), x=300.0, y=430.0)[0], "1")], name="0")
    a.connect([(r2, "2"), (a.add(msbuild.Donor(d, "GNDC"), x=650.0, y=520.0)[0], "1")], name="0")
    a.connect([(c1, "2"), (a.add(msbuild.Donor(d, "GNDC"), x=790.0, y=520.0)[0], "1")], name="0")

    node = n_in if where == "in" else n_mid
    wid, pts = wire_pts(a, node)
    print("[%s] 导线 %s pts=%s" % (where, wid, pts))
    vx = pick_vertex(pts)
    if vx is None:
        raise SystemExit("[%s] 导线没有中间顶点" % where)
    print("[%s] 探针落点 %s" % (where, vx))
    clone_probe_ext(a, PROBE_DONOR, vx[0], vx[1])

    out = os.path.join(ROOT, "out", "p17_%s.ms14" % where)
    n, _ = a.save(out)
    print("[%s] 写出 %s (%d 字节)" % (where, out, n))

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
        print("    node %-10s ports=%s" % (nd["ciid"], names))
    return out


if __name__ == "__main__":
    for w in ("in", "mid"):
        build(w)
