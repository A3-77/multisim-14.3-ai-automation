# -*- coding: utf-8 -*-
"""摸底：电位器参数索引 + 百分比->电阻 的对应关系。"""
import os
import sys
import json
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild  # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1")
os.makedirs(OUT, exist_ok=True)


def dump_pot_params():
    hit = msbuild.find_part("POTENTIOMETER", "POTENTIOMETER_VIRTUAL")
    print("donor:", hit)
    c = msbuild.load_donor(hit[0])
    d = msbuild.Donor(c, hit[1])
    ciid = d.ciid
    comp = None
    for el in c.elements:
        if el.get("CiID") == ciid:
            comp = el
            break
    print("pin_info:", {k: v["xy"] for k, v in c.pin_info(ciid).items()})

    def params_of(cc):
        for el in cc.elements:
            if el.get("CiID") == ciid:
                pl = el.find(".//CiaParamList")
                if pl is None:
                    return None
                dbl = [it.get("Value") for it in pl.find("doubles")]
                hum = [it.get("Value") for it in pl.find("parameters")]
                return dbl, hum
        return None

    print("原始:", params_of(c))

    # 逐个索引写入 10，看人类可读副本哪一项变成 10
    for i in range(8):
        c2 = msbuild.load_donor(hit[0])
        a = msbuild.Assembler()
        a.c = c2
        a.set_params(hit[1], {i: 10.0})
        print("idx %d -> %s" % (i, params_of(c2)))



if __name__ == "__main__":
    dump_pot_params()
