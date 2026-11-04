# -*- coding: utf-8 -*-
"""查看稳压管 donor 的模型定义。"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

hit = msbuild.find_part("ZENER", "1N4734A")
print("donor:", hit)
c = msbuild.load_donor(hit[0])
d = msbuild.Donor(c, hit[1])
print("model_item:", d.model_item is not None)
if d.model_item is not None:
    print(ET.tostring(d.model_item, encoding="unicode")[:2000])
print("pins:", c.pin_info(d.ciid))
