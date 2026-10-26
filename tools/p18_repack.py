# -*- coding: utf-8 -*-
"""P18: 分离「容器重打包」与「XML 重新序列化」两个变量。

L0  原生 Amplificador                          I(PR1)=13.9977 A
L1  过 Assembler/save（含 ET 重新序列化）        I(PR1)=0        ← 已知有损
R   只做容器重打包（明文 XML 字节原样写回）      → 若 I(PR1)=13.9977，说明
                                                 ET 的 XML 往返是元凶
S   只做 ET 往返后重打包（不经过 Assembler）     → 定位到 ET

用法: runtime\py32\python.exe tools\p18_repack.py
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "corpus", "samples14",
                   "Amplificador para resistencia de 1mOhm.ms14")

# R: 纯容器重打包
xml, info = dcl.read_ms14(SRC)
print("原生 info:", info, " 明文长度:", len(xml))
out_r = os.path.join(ROOT, "out", "p18_R_repack.ms14")
n, _ = dcl.write_ms14(out_r, xml)
print("R 写出 %s (%d 字节)" % (out_r, n))

# S: ET 往返（只 parse + serialize，不改任何东西）
tree = ET.fromstring(xml)
xml2 = ET.tostring(tree, encoding="ascii", xml_declaration=True)
print("ET 往返后长度: %d（原 %d，差 %+d）" % (len(xml2), len(xml), len(xml2) - len(xml)))
out_s = os.path.join(ROOT, "out", "p18_S_etround.ms14")
n, _ = dcl.write_ms14(out_s, xml2)
print("S 写出 %s (%d 字节)" % (out_s, n))

# 差异位置抽样
if len(xml2) != len(xml):
    for i in range(min(len(xml), len(xml2))):
        if xml[i:i+1] != xml2[i:i+1]:
            print("首个差异位置 %d:" % i)
            print("  原: %r" % xml[max(0, i-60):i+80])
            print("  新: %r" % xml2[max(0, i-60):i+80])
            break
