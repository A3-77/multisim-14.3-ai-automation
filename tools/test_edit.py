# -*- coding: utf-8 -*-
"""验证：改参数 + 重新压缩，Multisim 认不认。

把 SPICE Command Line 样例里的 R1 从 50Ω 改成 1kΩ，另存为 out/test_r1k.ms14。
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

src = [x for x in glob.glob(os.path.join(ROOT, "out", "samples", "*SPICE Command Line*"))][0]
c = msmodel.Circuit.from_xml_file(src)

r1 = c.find("R1")
print("改前:", c.params(r1["comp"])[:4])

# 参数槽 [1] 是主值（SPICE 模板里的 #1）
c.set_param(r1["comp"], 1, "1000.")

# 顺带把显示文字也换掉（单位缓存后缀保持不变）
item = c.symbol_of(r1["ciid"])
for el in item.iter():
    if el.tag == "CIITSymTextCompValue":
        old = el.get("Output")
        el.set("Output", "&UNI1000_uc103a9")
        print("显示文字:", old, "->", el.get("Output"))

print("改后:", c.params(r1["comp"])[:4])

out = os.path.join(ROOT, "out", "test_r1k.ms14")
n, body = c.save(out)
print("已写出 %s (%d 字节, 载荷 %d)" % (out, n, body))

back = msmodel.Circuit.load(out)
print("回读 R1 参数:", back.params(back.find("R1")["comp"])[:4])
