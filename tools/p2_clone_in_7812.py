# -*- coding: utf-8 -*-
"""P2 判定实验：在**原始 7812**（全部元件保留）里克隆一个新探针，绑 net3 顶点。

- 若 EnumOutputs 出现新探针 → 克隆路径没问题，祸根在剥离基底
- 若只有原探针 → 克隆路径仍有坑

输出 out/p2_clone7812.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

BASE = os.path.join(ROOT, "out", "rev_base.xml")
OUT = os.path.join(ROOT, "out", "p2_clone7812.ms14")

a = msbuild.Assembler(base_path=BASE)
print("7812 元件:", [c["refdes"] for c in a.c.components()])

# net3 的导线 93746496 顶点 (495,279)-(495,297)，取起点
ci, dr = a.add_probe("3", 495.0, 279.0, name="Probe9")
print("克隆探针 Probe9: CiID=%s 绘图ID=%s" % (ci, dr))

a.save(OUT)
print("写出 %s" % OUT)

back = a.c
print("回读 Probes:", end=" ")
import xml.etree.ElementTree as ET  # noqa: E402
for e in back.elements:
    if e.get("Class") == "CiCircuit":
        pr = e.find("CiCircuit/Probes")
        print([i.get("CiID") for i in pr] if pr is not None else None)
        break
