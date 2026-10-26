# -*- coding: utf-8 -*-
"""两个决定性实验（都在 COM 正常的 7812 基底上做反向验证）：

  expX: 7812 原样 + 把第一个 CiNode 的 Attributes 清空
        -> 若 EnumOutputs 失效，说明节点属性是 output 注册的必要条件
  expY: 7812 原样 + 探针位置改到 net0 的导线顶点 (558,288)，NetName 同步改 &ASC0
        -> 若正常，说明"位置顶点 + NetName 一致"就足以注册
  expZ: 7812 原样 + 只清空【探针自己所属网络】那个 CiNode 的 Attributes
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
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


def net_ciid_by_name(c, name):
    for e in c.elements:
        if e.get("Class") == "CiNode":
            if (e.find("CiNode").get("LocalName") or "").replace("&ASC", "") == name:
                return e.get("CiID")
    return None


def save(c, step):
    p = os.path.join(ROOT, "out", "p1_exp%s.ms14" % step)
    c.save(p)
    print("exp%s -> %s (%d B)" % (step, p, os.path.getsize(p)))


# ---- expX: 清空第一个 CiNode 的 Attributes ----
c = msmodel.Circuit.load(SRC)
n = 0
for e in c.elements:
    if e.get("Class") == "CiNode":
        at = e.find("CiNode/Attributes")
        if at is not None:
            for ch in list(at):
                at.remove(ch)
        n += 1
        if n >= 1:
            break
print("expX: 清空了 %d 个 CiNode 的 Attributes" % n)
save(c, "X")

# ---- expY: 探针移到 net0 顶点 (558,288)，NetName 同步 ----
c = msmodel.Circuit.load(SRC)
draw, elec = get_probe(c)
di = draw.find("CIITProbeComponent")
di.set("Transformer-M20", "558.")
di.set("Transformer-M21", "288.")
di.set("NetName", "&ASC0")
save(c, "Y")

# ---- expZ: 只清空探针所属网络（net4）那个 CiNode 的 Attributes ----
c = msmodel.Circuit.load(SRC)
target = net_ciid_by_name(c, "4")
print("expZ: net4 的 CiID =", target)
if target:
    for e in c.elements:
        if e.get("Class") == "CiNode" and e.get("CiID") == target:
            at = e.find("CiNode/Attributes")
            if at is not None:
                for ch in list(at):
                    at.remove(ch)
            print("  已清空 net4 的 Attributes")
            break
save(c, "Z")
