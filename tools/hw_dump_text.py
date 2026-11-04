# -*- coding: utf-8 -*-
"""看看元件符号里到底带了哪些"小字"（引脚编号等）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msmodel  # noqa: E402


def dump(path, refs):
    c = msmodel.Circuit.load(path)
    for ref in refs:
        ciid = [i["ciid"] for i in c.components() if i["refdes"] == ref][0]
        item = c.symbol_of(ciid)
        print("---", ref)
        for el in item.iter():
            if "Text" in el.tag:
                print("   %-28s Out=%-18r Hidden=%s  M20=%s M21=%s"
                      % (el.tag, el.get("Output"), el.get("Hidden"),
                         el.get("Transformer-M20"), el.get("Transformer-M21")))


if __name__ == "__main__":
    dump(sys.argv[1], sys.argv[2:])
