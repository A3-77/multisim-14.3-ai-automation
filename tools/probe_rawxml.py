# -*- coding: utf-8 -*-
"""关键测试：Multisim 能不能打开"不压缩"的 XML 电路文件？"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "out", "mem")
XML = open(os.path.join(MEM, "blob00.xml"), "rb").read()
print("XML:", len(XML), "bytes")

cands = {}

# A. 纯 XML
cands["plain.xml"] = XML

# B. 各种可能的"未压缩容器"布局
def hdr(name, size, flag=b"\x00\x00\x00\x00"):
    return name + struct.pack("<I", size) + b"\x00\x00\x00\x00" + struct.pack("<I", size) \
        + struct.pack("<I", size) + flag + XML

cands["b_msm_ewb.bin"] = hdr(b"MSMElectronicsWorkbench", len(XML))
cands["c_msm_ewb_xml.bin"] = hdr(b"MSMElectronicsWorkbenchXML", len(XML))
cands["d_compressed_name_raw.ms14"] = hdr(b"MSMCompressedElectronicsWorkbenchXML", len(XML))
cands["e_plain4c.ms14"] = hdr(b"MSMCompressedElectronicsWorkbenchXML4C\x02", len(XML))

for name, data in cands.items():
    p = os.path.join(MEM, name)
    open(p, "wb").write(data)
    print("写出 %-28s %d bytes" % (name, len(data)))

for name in cands:
    p = os.path.join(MEM, name)
    print("\n--- 尝试打开 %s ---" % name)
    try:
        with Multisim() as ms:
            c = ms.open(p)
            comps = c.components()
            print("   [OK] 打开成功! 电路名=%r 元件=%s" % (c.name, comps))
    except Exception as e:
        print("   [FAIL] %s" % str(e)[:220])
