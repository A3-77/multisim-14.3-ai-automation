# -*- coding: utf-8 -*-
"""P6-A：在**能跑的样例**上只克隆元件，不动原电路、不加探针、不连线。

A1: donor_spice + 克隆一个 RESISTOR_VIRTUAL（悬空）
A2: donor_spice + 克隆一个 DC_POWER（悬空）

若克隆后仍 running → 克隆元件路径无罪；
若变 stopped → 克隆元件就是祸根。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402
import msbuild  # noqa: E402

BASE = os.path.join(ROOT, "out", "_donor_spice.xml")


def build(out, refdes_src, new_refdes, kind):
    donor = msmodel.Circuit.from_xml_file(BASE)
    a = msbuild.Assembler(base_path=BASE)
    d = msbuild.Donor(donor, refdes_src)
    ci, ports = a.add(d, x=800.0, y=600.0, refdes=new_refdes)
    a.save(out)
    print("%s: 克隆 %s -> %s (CiID=%s)，写出 %s"
          % (kind, refdes_src, new_refdes, ci, os.path.basename(out)))


if __name__ == "__main__":
    build(os.path.join(ROOT, "out", "p6_a1_res.ms14"), "R1", "R9", "A1")
    build(os.path.join(ROOT, "out", "p6_a2_vsrc.ms14"), "V2", "V9", "A2")
