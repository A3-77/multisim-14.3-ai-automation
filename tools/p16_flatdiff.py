# -*- coding: utf-8 -*-
"""P16c: 同一文件内 buck R1 vs 克隆 R9 —— 全属性归一化逐元素 diff"""
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

SRC = os.path.join(ROOT, "out", "_p15_buckbase.xml")
IDRE = re.compile(r"\d{5,}")
GUIDRE = re.compile(r"\{[0-9A-Fa-f\-]{36}\}")


def flat(c, refdes):
    """把元件的对象子图摊平成 (class, 归一化属性) 列表"""
    ciid = c.find(refdes)["ciid"]
    comp_item = c._item_of(ciid)
    inner = comp_item.find("CiComponent")
    out = [("CiComponent", {k: v for k, v in inner.attrib.items()})]

    # 端口
    for it in inner.find("Ports").findall("Item"):
        port = c._item_of(it.get("CiID")).find("CiPort")
        out.append(("CiPort", dict(port.attrib)))

    # 符号子树
    for e in c.objects:
        li = list(e)
        if li and li[0].get("Class") == "CIITSymbolComp" and li[0].get("CiComponent") == ciid:
            for el in e.iter():
                out.append((el.get("Class") or el.tag, dict(el.attrib)))
            break

    # 引脚定义（符号 ConnectList 指向的）
    idmap = {}
    for el in c.tree.iter("Item"):
        if el.get("ID"):
            idmap.setdefault(el.get("ID"), el)
    defs = set()
    for e in c.objects:
        li = list(e)
        if li and li[0].get("Class") == "CIITSymbolComp" and li[0].get("CiComponent") == ciid:
            for cl in e.iter("ConnectList"):
                for it in cl.findall("Item"):
                    defs.add(it.get("ID"))
    for did in defs:
        d = idmap.get(did)
        if d is not None:
            for el in d.iter():
                out.append((el.get("Class") or el.tag, dict(el.attrib)))

    # 归一化
    norm = []
    for cls, at in out:
        na = {}
        for k, v in at.items():
            v2 = GUIDRE.sub("{G}", str(v))
            v2 = IDRE.sub("#", v2)
            na[k] = v2
        norm.append((cls, na))
    return norm


c = msmodel.Circuit.from_xml_file(SRC)
A = flat(c, "R1")
B = flat(c, "R9")
print("buck R1 元素 %d 个，克隆 R9 元素 %d 个" % (len(A), len(B)))

n = 0
for i in range(max(len(A), len(B))):
    ca, aa = A[i] if i < len(A) else ("<无>", {})
    cb, ab = B[i] if i < len(B) else ("<无>", {})
    if ca != cb:
        print("\n[%d] 类型不同: buck=%s  clone=%s" % (i, ca, cb))
        n += 1
        continue
    keys = sorted(set(aa) | set(ab))
    diffs = [(k, aa.get(k), ab.get(k)) for k in keys if aa.get(k) != ab.get(k)]
    if diffs:
        print("\n[%d] %s" % (i, ca))
        for k, va, vb in diffs:
            print("     %-30s buck=%-26s clone=%s" % (k, str(va)[:24], str(vb)[:40]))
        n += 1
    if n > 25:
        print("... 截断")
        break
print("\n差异元素数: %d" % n)
