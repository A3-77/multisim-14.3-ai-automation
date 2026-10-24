# -*- coding: utf-8 -*-
"""试所有主流压缩算法，在载荷的每个可能起点上。"""
import os
import zlib, bz2, lzma
import lz4.block, lz4.frame
import zstandard
import brotli

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
raw = open(os.path.join(OUT, "blank.xml"), "rb").read()
print("file size:", len(raw))

TARGET = 148145  # 头部记录的原始大小


def good(d):
    return d and len(d) > 1000 and (b"<?xml" in d[:200] or d.lstrip()[:1] == b"<")


results = []
for start in range(40, 80):
    pay = raw[start:]
    for label, fn in [
        ("lz4.block", lambda p: lz4.block.decompress(p, uncompressed_size=TARGET)),
        ("lz4.frame", lz4.frame.decompress),
        ("zstd", lambda p: zstandard.ZstdDecompressor().decompress(p, max_output_size=TARGET)),
        ("brotli", brotli.decompress),
        ("zlib", zlib.decompress),
        ("raw-deflate", lambda p: zlib.decompressobj(-15).decompress(p)),
        ("bz2", bz2.decompress),
        ("lzma", lzma.decompress),
    ]:
        try:
            d = fn(pay)
        except Exception:
            continue
        if d:
            results.append((start, label, len(d), d[:60]))
            if good(d):
                print("!!! HIT start=%d %s len=%d" % (start, label, len(d)))
                print(d[:500])
                open(os.path.join(OUT, "blank.decoded.xml"), "wb").write(d)
                raise SystemExit(0)

print("没有命中。可疑结果：")
for r in results[:10]:
    print("  start=%d %s len=%d head=%r" % r)
