# -*- coding: utf-8 -*-
"""P6-B：在**能跑的样例**上只用 Assembler.connect() 新建节点+导线，
把两个**已有**引脚连起来（不加新元件、不加探针）。

选脚：两个不同 net0（各自是独立的地符号节点）的引脚——
电气上是地-地零风险，完整走「新建 CiNode + 导线 + 端口重绑定」路径。

若仍 running → connect()/导线路径无罪；
若变 stopped → 祸根在 connect()。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402
import msbuild  # noqa: E402

BASE = os.path.join(ROOT, "out", "_donor_spice.xml")
OUT = os.path.join(ROOT, "out", "p6_b1_connect.ms14")

donor = msmodel.Circuit.from_xml_file(BASE)
a = msbuild.Assembler(base_path=BASE)

# 两个不同 net0 节点的引脚：
#   comp 737254680 pin2 -> net0-a（与 V1.pin1/pin3 同节点）
#   comp 737253880 pin2 -> net0-b（与另一个地符号同节点）
n = a.connect([("737254680", "2"), ("737253880", "2")], name="99")
print("新建节点 CiID=%s（连接 comp737254680.2 与 comp737253880.2）" % n)

a.save(OUT)
print("写出 %s" % OUT)

back = msmodel.Circuit.load(OUT)
print("回读:", back.summary())
