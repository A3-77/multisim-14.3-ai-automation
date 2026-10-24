# -*- coding: utf-8 -*-
"""探测 .ms14 头部里那个 '06' 到底是不是压缩方法号。

已知真实文件头（magic 之后 16 字节）：
    u32 uncompressedSize | u32 0 | u32 uncompressedSize | u32 compressedSize
紧接着 4 字节 01 06 20 01，再往后才是数据。
假设：第二字节 = ZIP 压缩方法（6 = implode）。若如此，方法 0 = 原样存储，
      那就能直接把明文 XML 塞进去，不需要自己实现压缩。
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out", "cand")
PY = sys.executable
OPEN_ONE = os.path.join(HERE, "open_one.py")

MAGIC_MSM = b"MSMCompressedElectronicsWorkbenchXML"
MAGIC_PLAIN = b"CompressedElectronicsWorkbenchXML"

xml_path = os.path.join(ROOT, "out", "mem", "blob00.xml")
xml = open(xml_path, "rb").read()
n = len(xml)
print("XML %d 字节" % n)


def build(magic, prefix, unc=None, comp=None):
    unc = n if unc is None else unc
    comp = n if comp is None else comp
    return magic + struct.pack("<IIII", unc, 0, unc, comp) + prefix + xml


cands = {
    "a_msm_m0_20_01": build(MAGIC_MSM, b"\x01\x00\x20\x01"),
    "b_msm_m0_00_00": build(MAGIC_MSM, b"\x00\x00\x00\x00"),
    "c_msm_m0_2b": build(MAGIC_MSM, b"\x01\x00"),
    "d_msm_m0_none": build(MAGIC_MSM, b""),
    "e_plain_m0": build(MAGIC_PLAIN, b"\x01\x00\x20\x01"),
    "f_msm_m6_ctrl": build(MAGIC_MSM, b"\x01\x06\x20\x01"),
    "g_msm_m0_20_00": build(MAGIC_MSM, b"\x01\x00\x20\x00"),
}

os.makedirs(OUT, exist_ok=True)
results = []
for name, blob in cands.items():
    p = os.path.join(OUT, name + ".ms14")
    with open(p, "wb") as f:
        f.write(blob)
    try:
        r = subprocess.run([PY, OPEN_ONE, p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        print("%-18s -> rc=%-3s %s" % (name, r.returncode, out[:120]))
    except subprocess.TimeoutExpired:
        print("%-18s -> 超时" % name)
    results.append((name, p))

print("\n文件都在", OUT)
