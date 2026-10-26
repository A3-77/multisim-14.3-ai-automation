# -*- coding: utf-8 -*-
"""验证：探针 Transformer 坐标的尾点格式是否是 EnumOutputs 失效的原因。

  step5: 改 NetName + 位置带尾点 "400."/"300."（7812 里 (400,300) 是空白处）
  step6: 改 NetName + 位置带尾点 "558."/"234."（保持原位，只验证格式）
  step7: 改 NetName + 位置带尾点，且放在 7812 的某个网络上
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import msmodel  # noqa: E402

SRC = os.path.join(ROOT, "samples", "7812.ms12")


def get_probe(c):
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeComponent":
            draw = e
            break
    for e in c.elements:
        if e.get("Class") == "CiProbeComp":
            elec = e
            break
    return draw, elec


# 7812 的 net4 上有什么点？U1 的 OUT 引脚在 net4。先找 U1 引脚坐标。
def net_points(c):
    """返回 {网络名: [(x,y), ...]}"""
    pts = {}
    for e in c.elements:
        if e.get("Class") != "CiPort":
            continue
        p = e.find("CiPort")
        # 找该引脚所属网络名
        nd = p.find("Nodes")
        if nd is None:
            continue
        for n in c.elements:
            if n.get("Class") != "CiNode":
                continue
            if any(i.get("CiID") == e.get("CiID") for i in n.find("CiNode/Ports")):
                nm = (n.find("CiNode").get("LocalName") or "").replace("&ASC", "")
                # 引脚坐标
                comp = p.get("Component")
                info = c.pin_info(comp)
                for k, v in info.items():
                    if v.get("port") == e.get("CiID"):
                        pts.setdefault(nm, []).append(v["xy"])
    return pts


c0 = msmodel.Circuit.load(SRC)
pts = net_points(c0)
print("7812 各网络的引脚坐标：")
for k, v in sorted(pts.items()):
    print("  net%-4s %s" % (k, [(round(a, 1), round(b, 1)) for a, b in v]))


def build(step, x, y, with_dot):
    c = msmodel.Circuit.load(SRC)
    draw, elec = get_probe(c)
    di = draw.find("CIITProbeComponent")
    di.set("NetName", "&ASC1")
    di.set("Transformer-M20", ("%g." % x) if with_dot else ("%g" % x))
    di.set("Transformer-M21", ("%g." % y) if with_dot else ("%g" % y))
    out = os.path.join(ROOT, "out", "p1_step%d.ms14" % step)
    c.save(out)
    print("step%d -> %s  M20=%r M21=%r" % (step, out, di.get("Transformer-M20"),
                                           di.get("Transformer-M21")))
    return out


# net1 上的一个点（7812 里 net1 是 AC1/V- 那条）
target = None
for nm, v in pts.items():
    if nm == "1" and v:
        target = v[0]
        break
print("\nnet1 上的点:", target)

build(5, 400, 300, True)      # 带尾点，空白处
build(6, 558, 234, True)      # 带尾点，原位
if target:
    build(7, target[0], target[1], True)   # 带尾点，net1 上的点
