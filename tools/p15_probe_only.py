# -*- coding: utf-8 -*-
"""P15 最干净的对照：donor 文件**一个连接都不改**，只在现有导线顶点放一个探针。

用来分离两个变量：
  donor 本身能否仿真（若能，读到非 0 -> 我的"重新接线"操作是问题）
  donor 本身就不能仿真（读到 0 或没输出 -> 问题在文件/元件层面，与接线无关）

donor_spice 的 node2 = C2.1 + L2.2 + R1.1，导线顶点 (486,225)。
R1.2 直接接地，所以 node2 是有直流通路的真实节点。

用法：python tools/p15_probe_only.py
产物：out/p15_probe_only.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

BASE = os.path.join(ROOT, "out", "_donor_spice.xml")
OUT = os.path.join(ROOT, "out", "p15_probe_only.ms14")
# donor 的 node2 导线上一个真实顶点（来自 wire 列表：(486,261)-(486,225)）
PROBE_XY = (486.0, 225.0)


def main():
    a = msbuild.Assembler(base_path=BASE)
    c = a.c
    print("donor 元件（全原装，不改任何连接）:")
    for x in c.components():
        print("   %-5s %-34s" % (x["refdes"], x["part"]))
    print("donor 网络:")
    pm = {q["ciid"]: q for q in c.ports()}
    for nd in c.nodes():
        names = []
        for pid in nd["ports"]:
            q = pm.get(pid)
            if q:
                ref = next((y["refdes"] for y in c.components()
                            if y["ciid"] == q["component"]), "?")
                names.append("%s.%s" % (ref, q["name"]))
        print("   node %-10s name=%-4r %s" % (nd["ciid"], nd["name"], names))

    clone_probe_ext(a, PROBE_DONOR, *PROBE_XY)
    print("\n探针 @ %s（node2 导线顶点，未改任何连接）" % (PROBE_XY,))

    n, _ = a.save(OUT)
    print("写出 %s (%d 字节)" % (OUT, n))
    back = msmodel.Circuit.load(OUT)
    print("回读网络数:", len(back.nodes()), " 元件数:", len(back.components()))


if __name__ == "__main__":
    main()
