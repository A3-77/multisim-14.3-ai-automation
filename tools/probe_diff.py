# -*- coding: utf-8 -*-
"""比较两个空白电路的载荷，判断是"压缩"还是"加密"，并试探 LZSS 家族。"""
import os, zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")


def parse(path):
    raw = open(path, "rb").read()
    # 头部：ASCII 名字，直到出现非 ASCII
    i = 0
    while i < len(raw) and 32 <= raw[i] < 127:
        i += 1
    name = raw[:i].decode("latin-1")
    rest = raw[i:]
    print("%-14s name=%r  after=%s" % (os.path.basename(path), name, rest[:16].hex(" ")))
    # 找载荷起点：两个 4 字节大小之后
    return raw, i


a, ia = parse(os.path.join(OUT, "blank.xml"))
b, ib = parse(os.path.join(OUT, "blank.ms14"))

# 载荷起点：从名字末尾跳过 4+4+4+4 字节
for off_a in range(ia, ia + 24):
    for off_b in range(ib, ib + 24):
        n = 0
        while off_a + n < len(a) and off_b + n < len(b) and a[off_a + n] == b[off_b + n]:
            n += 1
        if n > 100:
            print("offset a=%d b=%d 共同前缀=%d 字节" % (off_a, off_b, n))
            print("  a 前 32:", a[off_a:off_a + 32].hex(" "))
            print("  b 前 32:", b[off_b:off_b + 32].hex(" "))
