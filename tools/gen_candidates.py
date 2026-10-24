# -*- coding: utf-8 -*-
"""生成一批"未压缩"候选文件：改压缩方法标志位，载荷直接放明文 XML。"""
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "out", "mem")
XML = open(os.path.join(MEM, "blob00.xml"), "rb").read()
N = len(XML)

names = [
    b"MSMCompressedElectronicsWorkbenchXML",
    b"MSMElectronicsWorkbenchXML",
    b"MSMElectronicsWorkbench",
]
flags = [b"\x00\x06\x20\x01", b"\x00\x00\x00\x00", b"\x01\x06\x20\x01", b"\x02\x06\x20\x01"]

made = []
for nm in names:
    for fl in flags:
        tag = "%s_%s" % (nm.decode()[3:18], fl.hex())
        p = os.path.join(MEM, "cand_%s.ms14" % tag)
        with open(p, "wb") as f:
            f.write(nm)
            f.write(struct.pack("<I", N))
            f.write(b"\x00\x00\x00\x00")
            f.write(struct.pack("<I", N))
            f.write(struct.pack("<I", N))
            f.write(fl)
            f.write(XML)
        made.append(p)

# 再来几个不带尺寸字段的
for nm in names:
    p = os.path.join(MEM, "cand_%s_nosize.ms14" % nm.decode()[3:18])
    with open(p, "wb") as f:
        f.write(nm)
        f.write(b"\x00")
        f.write(XML)
    made.append(p)

print("生成 %d 个候选" % len(made))
for p in made:
    print("  " + os.path.basename(p))
