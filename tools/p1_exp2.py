# -*- coding: utf-8 -*-
"""修正实验：确认"探针位置必须是导线顶点（不是引脚坐标、不是线段中间）"。

  expY2: 7812，探针移到 net0 的真实导线顶点 (495,333)，NetName=&ASC0
  expY3: 7812，探针移到 net0 导线顶点 (576,324)，NetName=&ASC0
  expA1: acceptance_v2，探针1 移到 net1 导线中间顶点 (513,300)（非引脚坐标）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402


def get_probe(c, idx=0):
    draws = []
    for e in c.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeComponent":
            draws.append(e)
    elecs = [e for e in c.elements if e.get("Class") == "CiProbeComp"]
    return draws[idx], elecs[idx]


def save(c, tag):
    p = os.path.join(ROOT, "out", "p1_%s.ms14" % tag)
    c.save(p)
    print("%s -> %s (%d B)" % (tag, p, os.path.getsize(p)))
    return p


# ---- expY2 / expY3：7812 上把探针移到 net0 的真实导线顶点 ----
for tag, xy, net in (("expY2", (495, 333), "0"), ("expY3", (576, 324), "0")):
    c = msmodel.Circuit.load(os.path.join(ROOT, "samples", "7812.ms12"))
    draw, elec = get_probe(c)
    di = draw.find("CIITProbeComponent")
    di.set("Transformer-M20", "%g." % xy[0])
    di.set("Transformer-M21", "%g." % xy[1])
    di.set("NetName", "&ASC" + net)
    save(c, tag)

# ---- expA1：acceptance_v2 上把 Probe1 移到 net1 导线顶点 (513,300) ----
c = msmodel.Circuit.load(os.path.join(ROOT, "out", "p1_acceptance_v2.ms14"))
draw, elec = get_probe(c, 0)
di = draw.find("CIITProbeComponent")
di.set("Transformer-M20", "513.")
di.set("Transformer-M21", "300.")
di.set("NetName", "&ASC1")
save(c, "expA1")

# ---- expA2：acceptance_v2 上把 Probe1 移到 net0 导线顶点 (513,336) ----
c = msmodel.Circuit.load(os.path.join(ROOT, "out", "p1_acceptance_v2.ms14"))
draw, elec = get_probe(c, 0)
di = draw.find("CIITProbeComponent")
di.set("Transformer-M20", "513.")
di.set("Transformer-M21", "336.")
di.set("NetName", "&ASC0")
save(c, "expA2")
