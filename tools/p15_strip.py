# -*- coding: utf-8 -*-
"""P15 A/B 准备：从已生成文件里剥掉 RefDes 注册，得到对照文件。

用法：python tools/p15_strip.py out/p15_probe.ms14 out/p15_probe_noref.ms14
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl  # noqa: E402


def strip(src, dst):
    xml, _ = dcl.read_ms14(src)
    tree = ET.fromstring(xml)
    n = 0
    for cont in tree.iter("CIRToInfoMap"):
        for it in list(cont):
            cont.remove(it)
            n += 1
    for usage in tree.iter("RefDesPrefixUsageMap"):
        for it in list(usage):
            usage.remove(it)
    out = ET.tostring(tree, encoding="ascii", xml_declaration=True)
    size, _ = dcl.write_ms14(dst, out)
    print("剥掉 %d 条 RefDes 注册 -> %s (%s 字节)" % (n, dst, size))
    return n


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "p15_probe.ms14")
    b = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "out", "p15_probe_noref.ms14")
    strip(a, b)
