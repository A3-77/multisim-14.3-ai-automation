# -*- coding: utf-8 -*-
"""检查画出来的导线有没有"看着像连上了"的隐患。

Multisim 的电气连通性只看 CiNode/Ports，跟画面无关 —— 所以「图上画错」和
「电气连错」是两回事。这个脚本只查**画面**上的三类硬伤：

  1. 两条不同网络的导线**共线重叠**（看起来就是一根线，等于短路）；
  2. 一条导线的顶点**正好落在另一条导线的线段上**（会画出一个结点）；
  3. 一条导线的线段**正好穿过别的元件的引脚**（Multisim 可能自动连上）。

垂直交叉（X 形、没有结点）是正常的原理图画法，**不报**。

用法：python tools/hw_wires.py out/hw1/sch2.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msmodel  # noqa: E402

EPS = 0.6


def _load(path):
    c = msmodel.Circuit.load(path)
    comps = {i["ciid"]: i["refdes"] for i in c.components()}
    pins = []
    for ciid, ref in comps.items():
        for name, d in c.pin_info(ciid).items():
            if d.get("xy"):
                pins.append((ref, name, round(d["xy"][0], 2), round(d["xy"][1], 2)))

    # 导线：CIITLinkComp/Points + Node(CiNode CiID)
    node_name = {}
    for n in c.nodes():
        node_name[n["ciid"]] = n["name"] or n["ciid"]

    wires = []
    for el in c.diagram.iter():
        if el.get("Class") != "CIITLinkComp":
            continue
        inner = el.find("CIITLinkComp")
        if inner is None:
            continue
        pts = [(round(float(p.get("X")), 2), round(float(p.get("Y")), 2))
               for p in inner.findall("Points/Item")]
        if len(pts) < 2:
            continue
        wires.append({"node": node_name.get(inner.get("Node"), inner.get("Node")),
                      "pts": pts})
    return comps, pins, wires


def _segs(w):
    return [(w["pts"][i], w["pts"][i + 1]) for i in range(len(w["pts"]) - 1)]


def _on_seg(p, a, b):
    """p 是否落在线段 ab 上（含端点）。"""
    (px, py), (ax, ay), (bx, by) = p, a, b
    if abs(ax - bx) <= EPS:                       # 竖直线段
        return abs(px - ax) <= EPS and min(ay, by) - EPS <= py <= max(ay, by) + EPS
    if abs(ay - by) <= EPS:                       # 水平线段
        return abs(py - ay) <= EPS and min(ax, bx) - EPS <= px <= max(ax, bx) + EPS
    return False


def check(path):
    _c, pins, wires = _load(path)
    print("=== %s" % os.path.basename(path))
    print("导线 %d 条，顶点 %d 个" % (len(wires), sum(len(w["pts"]) for w in wires)))
    bad = 0

    # 1) 共线重叠：两条不同网络的线段在同一条直线上且有交集
    for i in range(len(wires)):
        for j in range(i + 1, len(wires)):
            if wires[i]["node"] == wires[j]["node"]:
                continue
            for a1, a2 in _segs(wires[i]):
                for b1, b2 in _segs(wires[j]):
                    if (abs(a1[1] - a2[1]) <= EPS and abs(b1[1] - b2[1]) <= EPS
                            and abs(a1[1] - b1[1]) <= EPS):
                        lo = max(min(a1[0], a2[0]), min(b1[0], b2[0]))
                        hi = min(max(a1[0], a2[0]), max(b1[0], b2[0]))
                        if hi - lo > EPS:
                            print("  !! 共线重叠(水平) y=%.2f x=[%.2f,%.2f]  net %s / %s"
                                  % (a1[1], lo, hi, wires[i]["node"], wires[j]["node"]))
                            bad += 1
                    if (abs(a1[0] - a2[0]) <= EPS and abs(b1[0] - b2[0]) <= EPS
                            and abs(a1[0] - b1[0]) <= EPS):
                        lo = max(min(a1[1], a2[1]), min(b1[1], b2[1]))
                        hi = min(max(a1[1], a2[1]), max(b1[1], b2[1]))
                        if hi - lo > EPS:
                            print("  !! 共线重叠(竖直) x=%.2f y=[%.2f,%.2f]  net %s / %s"
                                  % (a1[0], lo, hi, wires[i]["node"], wires[j]["node"]))
                            bad += 1

    # 2) 顶点压在别的网络的线段上
    for i in range(len(wires)):
        for j in range(len(wires)):
            if i == j or wires[i]["node"] == wires[j]["node"]:
                continue
            for p in wires[i]["pts"]:
                for a, b in _segs(wires[j]):
                    if _on_seg(p, a, b):
                        print("  !! 顶点(%.2f,%.2f) net %s 压在线段 %s->%s (net %s) 上"
                              % (p[0], p[1], wires[i]["node"], a, b, wires[j]["node"]))
                        bad += 1

    # 3) 导线**中段**穿过别的元件引脚（端点上就是它自己接的引脚，正常）
    for w in wires:
        for a, b in _segs(w):
            for ref, name, px, py in pins:
                if not _on_seg((px, py), a, b):
                    continue
                at_end = (abs(px - a[0]) <= EPS and abs(py - a[1]) <= EPS) or \
                         (abs(px - b[0]) <= EPS and abs(py - b[1]) <= EPS)
                if at_end:
                    continue
                print("  !! 导线(net %s) %s->%s 中段穿过引脚 %s.%s (%.2f,%.2f)"
                      % (w["node"], a, b, ref, name, px, py))
                bad += 1

    # 4) 斜线段。原理图里导线必须横平竖直 —— 一旦出现明显的斜线，
    #    说明折点顺序写反了（wire_via 的路径是 [引脚] + 折点 + [枢纽]，
    #    折点要按"从引脚走向枢纽"的顺序给，给反了最后一段就会斜着跳回去）。
    #    容差 3 个单位：图纸坐标缩放后会有零点几的浮点残差，看不见。
    for w in wires:
        for a, b in _segs(w):
            dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
            if dx > 3.0 and dy > 3.0:
                print("  !! 斜线(net %s) %s->%s  (Δx=%.2f, Δy=%.2f)"
                      % (w["node"], a, b, dx, dy))
                bad += 1

    print("  没有发现问题" if bad == 0 else "  共 %d 处隐患" % bad)
    return bad


if __name__ == "__main__":
    n = 0
    for p in sys.argv[1:]:
        n += check(p)
    sys.exit(1 if n else 0)
