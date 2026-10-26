# -*- coding: utf-8 -*-
"""对照实验：把 7812.ms12 用自研 dcl 重新压缩成 .ms14，看 COM 还能不能枚举出探针。
用于区分"压缩器问题"还是"克隆问题"。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402

SRC = os.path.join(ROOT, "samples", "7812.ms12")
DST = os.path.join(ROOT, "out", "p1_7812_recompressed.ms14")

xml, info = dcl.read_ms14(SRC)
print("解出 %d 字节" % len(xml))
n, body = dcl.write_ms14(DST, xml)
print("重压缩 -> %s（文件 %d 字节，压缩体 %d 字节，原文件 %d 字节）"
      % (DST, n, body, os.path.getsize(SRC)))

# 回读校验
xml2, _ = dcl.read_ms14(DST)
print("往返一致:", xml2 == xml)
