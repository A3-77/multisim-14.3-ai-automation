# -*- coding: utf-8 -*-
"""P9：p7_isolate（V2=5V + R1=1k + GND 回路）上加老式探针，读 5V。

p8 已证明自建电路可仿真（纯电阻回路瞬态瞬间完成，state 立刻 stopped 是正常现象）。
本实验：在 net1（V2.1/R1.1 节点）的导线顶点上放老式探针，
看 EnumOutputs 是否注册、dc_op 是否读到 ~5V。

输出 out/p9_probe.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402
import msbuild  # noqa: E402

BASE = os.path.join(ROOT, "out", "_p7_isolate.xml")
OUT = os.path.join(ROOT, "out", "p9_probe.ms14")

a = msbuild.Assembler(base_path=BASE)
ref2ciid = {c["refdes"]: c["ciid"] for c in a.c.components()}
V2 = ref2ciid["V2"]
print("基底元件:", [c["refdes"] for c in a.c.components()])

# net1 导线顶点：connect() 画的 V2.1—R1.1，取 V2.1 引脚坐标
info = a.c.pin_info(V2)
print("V2 引脚:", {k: v["xy"] for k, v in info.items()})
x, y = info["1"]["xy"]
print("探针放 net1 导线顶点 (%g,%g)" % (x, y))

ci, dr = a.add_probe("1", x, y, name="Probe1")
print("Probe1: CiID=%s 绘图ID=%s" % (ci, dr))

a.save(OUT)
print("写出 %s" % OUT)

back = msmodel.Circuit.load(OUT)
for e in back.elements:
    if e.get("Class") == "CiCircuit":
        pr = e.find("CiCircuit/Probes")
        print("Probes 注册:", [i.get("CiID") for i in pr] if pr is not None else None)
        break
