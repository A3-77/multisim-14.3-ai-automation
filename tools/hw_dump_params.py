# -*- coding: utf-8 -*-
"""打印指定 .ms14 里某个元件的 CiaParamList（doubles + parameters 字符串）。"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msbuild          # noqa: E402
import msmodel          # noqa: E402


def dump(path, refs=None):
    c = msbuild.load_donor(path)
    for item in c.components():
        name = item["refdes"]
        if refs and name not in refs:
            continue
        fam, part = item["family"], item["part"]
        comp = item["comp"]
        attrs = comp.find("Attributes")
        pl = attrs[msmodel.ATTR_PARAMS].find("CiaParamList")
        print("%-6s %s/%s" % (name, fam, part))
        if pl is None:
            print("       无 CiaParamList")
            continue
        d = pl.find("doubles")
        nums = [x.get("Value") for x in d.findall("Item")] if d is not None else []
        ps_el = pl.find("parameters")
        ps = [x.get("Value") for x in ps_el.findall("Item")] if ps_el is not None else []
        print("       doubles(%d)=%s" % (len(nums), nums))
        for i, s in enumerate(ps):
            print("       param[%d] = %r" % (i, s))


if __name__ == "__main__":
    p = sys.argv[1]
    refs = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    print("文件:", p)
    dump(p, refs)
