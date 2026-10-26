# -*- coding: utf-8 -*-
"""最小改动二分：从 COM 正常的 7812 出发，逐项加改动，定位哪一项导致 EnumOutputs 变空。

  step1: 只改探针 NetName  &ASC4 -> &ASC1
  step2: + 改 Transformer-M20/M21 -> 400/300
  step3: + 改 CiProbeComp.LocalName -> &ASCProbe1
  step4: + 全套换新 ID（绘图 ID / 电气 CiID / SymCompID / CiProbeComp 回指 / ConnectList 引脚定义）
  step5: + 注册到 CiCircuit/Probes 用新 CiID（step4 已包含）
  每步输出一个文件：out/p1_step{N}.ms14
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402
import msmodel  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SRC = os.path.join(ROOT, "samples", "7812.ms12")


def get_probe(c):
    draw = elec = None
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


def build(step):
    c = msmodel.Circuit.load(SRC)
    draw, elec = get_probe(c)
    di = draw.find("CIITProbeComponent")
    ei = elec.find("CiProbeComp")

    if step >= 1:
        di.set("NetName", "&ASC1")
    if step >= 2:
        di.set("Transformer-M20", "400")
        di.set("Transformer-M21", "300")
    if step >= 3:
        ei.set("LocalName", "&ASCProbe1")
    if step >= 4:
        # 全套换新 ID
        old_draw = draw.get("ID")
        old_elec = elec.get("CiID")
        new_draw = c.new_id()
        new_elec = c.new_id()
        draw.set("ID", new_draw)
        elec.set("CiID", new_elec)
        di.set("CiProbeComp", new_elec)
        ei.set("SymCompID", new_draw)
        ei.set("InstanceID", "&ASC{%s}" % str(__import__("uuid").uuid4()).upper())
        # ConnectList 引脚定义换新
        rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
        defs = {it.get("ID"): it for it in rc}
        for it in di.findall(".//ConnectList/Item"):
            old = it.get("ID")
            if old in defs:
                nd = copy.deepcopy(defs[old])
                nid = c.new_id()
                nd.set("ID", nid)
                rc.append(nd)
                it.set("ID", nid)
        # Probes 注册换新
        for e in c.elements:
            if e.get("Class") == "CiCircuit":
                pr = e.find("CiCircuit/Probes")
                if pr is not None:
                    for i in pr:
                        if i.get("CiID") == old_elec:
                            i.set("CiID", new_elec)
                break
        # 引脚定义的 CenterX/Y 也要跟着位置走（step2 改了位置）
        if step >= 2:
            for it in di.findall(".//ConnectList/Item"):
                pass  # 引脚定义保持原位，只测 output 枚举，不管几何

    out = os.path.join(ROOT, "out", "p1_step%d.ms14" % step)
    c.save(out)
    print("step%d -> %s (%d 字节)" % (step, out, os.path.getsize(out)))
    return out


for s in (1, 2, 3, 4):
    build(s)
