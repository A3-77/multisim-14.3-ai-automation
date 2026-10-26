# -*- coding: utf-8 -*-
"""P18 阶梯实验：把「基底 + 保存路径」和「克隆/连线」两件事分开。

L0: 原生 Amplificador para resistencia de 1mOhm.ms14 → 已实测可跑
    （V(PR1)=84V, I(PR1)=13.9977A, P(PR3)=0.1959W）
L1: 同一文件，过一遍 Assembler(base) + save()，**不加任何元件**
    → 若结果与 L0 完全一致，说明基底和保存路径没问题
L2: 在 L1 基础上克隆一个 1MΩ 电阻并接到 GND（只加一个元件）
    → 若输出不变，说明克隆件是死的；若变化，说明克隆有效

用法: runtime\py32\python.exe tools\p18_ladder.py
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
import mssafe

D = os.path.join(ROOT, "corpus", "samples14")
SRC = os.path.join(D, "Amplificador para resistencia de 1mOhm.ms14")
XML = os.path.join(ROOT, "out", "_amp_base.xml")

# 1) 把原生文件解成 XML 供 Assembler 当基底
c0 = msmodel.Circuit.load(SRC)
with open(XML, "wb") as f:
    f.write(mssafe.serialize(c0.tree))
print("基底 XML:", XML, os.path.getsize(XML), "字节")

# 2) L1：只过一遍保存路径
a = msbuild.Assembler(base_path=XML)
out1 = os.path.join(ROOT, "out", "p18_L1.ms14")
n, _ = a.save(out1)
print("L1 写出 %s (%d 字节)" % (out1, n))

# 3) L2：克隆一个电阻，跨接到已有节点（并联在 R1 上，值取 1MΩ 影响很小）
b = msbuild.Assembler(base_path=XML)
d = msbuild.load_donor(SRC)
comps = d.components()
print("基底元件:", [(x["refdes"], x["part"]) for x in comps])
# 找一个虚拟电阻和一个地
rref = next(x["refdes"] for x in comps if x["part"] == "RESISTOR_VIRTUAL")
gnds = [x for x in comps if x["part"] == "GROUND"]
print("用于克隆的 R=%s, GND 数=%d" % (rref, len(gnds)))
