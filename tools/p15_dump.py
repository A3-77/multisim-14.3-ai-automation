# -*- coding: utf-8 -*-
"""dump 一个样例文件的元件/网络/地符号，用于挑选 donor 模板。

用法：python tools/p15_dump.py corpus/samples/Analog__SpeechFilter.xml.gz
"""
import glob
import gzip
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel


def load(p):
    try:
        return msmodel.Circuit.load(p)
    except Exception:
        pass
    if p.endswith(".gz"):
        return msmodel.Circuit(gzip.open(p, "rb").read())
    return msmodel.Circuit.from_xml_file(p)


def resolve(p):
    """支持三种写法：绝对路径 / 索引里的 rel（如 Analog\\SpeechFilter.ms14）/ 关键字。"""
    if os.path.isabs(p) and os.path.exists(p):
        return p
    import json
    idx = json.load(open(os.path.join(ROOT, "corpus", "samples_index.json"),
                         encoding="utf-8"))
    key = p.replace("/", "\\").lower()
    for e in idx:
        rel = (e.get("rel") or "").lower()
        if rel == key or os.path.basename(rel) == key:
            return e["file"]
    hits = [e for e in idx if key in (e.get("rel") or "").lower()]
    if len(hits) == 1:
        return hits[0]["file"]
    if hits:
        print("匹配到多个，用第一个：")
        for e in hits[:8]:
            print("   ", e["rel"])
        return hits[0]["file"]
    raise SystemExit("找不到样例 %r" % p)


def main():
    p = resolve(sys.argv[1])
    c = load(p)
    print("==", os.path.basename(p))
    print("元件:")
    for x in c.components():
        print("   %-6s %-34s %s" % (x["refdes"], x["part"], x["ciid"]))
    gnds = [x for x in c.components() if x["part"] == "GROUND"]
    print("地符号: %d 个" % len(gnds))
    print("网络:")
    pm = {q["ciid"]: q for q in c.ports()}
    for nd in c.nodes():
        names = []
        for pid in nd["ports"]:
            q = pm.get(pid)
            if q:
                ref = next((y["refdes"] for y in c.components()
                            if y["ciid"] == q["component"]), "?")
                names.append("%s.%s" % (ref, q["name"]))
        print("   node %-10s name=%-4r %s" % (nd["ciid"], nd["name"], names))


if __name__ == "__main__":
    main()
