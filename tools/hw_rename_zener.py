# -*- coding: utf-8 -*-
"""把稳压管 donor 里"元件名"那几个字符串从 1N4734A 改成 02DZ4.7。

模型串（.MODEL ...）在 hw_make_zener.py 里已经改过（BV=4.7），
这里只改**位号旁边显示的那个型号**，让图上和作业的元件表对得上。
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

SRC = os.path.join(ROOT, "out", "hw1", "donors", "zener_4v7.ms14")
BAK = os.path.join(ROOT, "out", "hw1", "donors", "zener_4v7.bak.ms14")

if not os.path.isfile(BAK):
    shutil.copy2(SRC, BAK)
    print("备份 ->", BAK)

c = msbuild.load_donor(SRC)
n = 0
for el in c.elements:
    for it in el.iter("Item"):
        if (it.get("Value") or "") == "&ASC1N4734A":
            it.set("Value", "&ASC02DZ4.7")
            n += 1
print("改名 %d 处" % n)
c.save(SRC)
print("写出", SRC, os.path.getsize(SRC), "字节")
