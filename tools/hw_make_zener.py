# -*- coding: utf-8 -*-
"""做一个 4.7 V 稳压管的 donor 文件（作业图 2 用的是 02DZ4.7）。

元件库里只有 1N4734A（5.6 V）。稳压管的击穿电压就写在它内联的 SPICE 模型串里
（BV= 5.624），所以直接克隆一份、把 BV 改成 4.7、名字改成 02DZ4.7，
就是一个货真价实的 4.7 V 稳压管 —— 不是拿 5.6 V 凑数。
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1", "donors")
os.makedirs(OUT, exist_ok=True)
TARGET = os.path.join(OUT, "zener_4v7.ms14")


def main():
    if os.path.isfile(TARGET):
        print("已存在，跳过：", TARGET)
        return TARGET
    hit = msbuild.find_part("ZENER", "1N4734A")
    a = msbuild.Assembler()
    d = msbuild.Donor(msbuild.load_donor(hit[0]), hit[1])
    ciid, ports = a.add(d, x=500.0, y=400.0, refdes="D1")

    comp = None
    for el in a.els:
        if el.get("CiID") == ciid:
            comp = el
            break
    inner = comp.find("CiComponent")
    model_id = inner.get("Model")
    model = None
    for el in a.els:
        if el.get("CiID") == model_id:
            model = el
            break
    if model is None:
        raise RuntimeError("找不到模型对象")

    n = 0
    for el in model.iter("CiaCString"):
        s = el.get("String") or ""
        if "1N4734A" not in s:
            continue
        s2 = (s.replace("1N4734A__ZENER__1", "02DZ4_7__ZENER__1")
               .replace("1N4734A", "02DZ4.7")
               .replace("BV= 5.624", "BV= 4.7"))
        el.set("String", s2)
        n += 1
    mi = model.find("CiModel")
    if mi is not None:
        mi.set("LocalName", "&ASC02DZ4_7__ZENER__1")
    print("改写模型串 %d 处" % n)

    a.save(TARGET)
    print("写出", TARGET, os.path.getsize(TARGET), "字节")

    # 回读确认
    c = msbuild.load_donor(TARGET)
    for d2 in c.components():
        print("回读:", d2["refdes"], d2["family"], d2["part"])
    return TARGET


if __name__ == "__main__":
    main()
