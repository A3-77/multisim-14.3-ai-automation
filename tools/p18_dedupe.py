# -*- coding: utf-8 -*-
"""给 .ms14 里所有元件的绘图子对象重新分配唯一 ID。

背景：msbuild.Assembler.add() 克隆元件时，只给「元件 / 符号顶层 / 引脚 CiPort」
换了新 ID，符号内部的图元（本体折线 CODMultiLineComp、引脚符号 CIITPinSymbolComp、
引脚连接点 CIITPinConnectorComp、名称/数值文字）仍然沿用 donor 的旧 ID。
从同一个 donor 克隆两个元件时（例如 R1、R2），它们的子对象 ID 完全相同；
Multisim 的对象表按 ID 索引，后写覆盖先写 —— 先克隆的那个元件在画布上直接不显示，
电气上也等于不存在。这与「连通性表正确、元件却开路、探针读 0V」的现象吻合。

用法：
    python tools/p18_dedupe.py in.ms14 out.ms14
"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dcl

TEXT_CLASSES = {
    "CIITSymTextCompName", "CIITSymTextCompValue", "CIITSymTextCompLocation",
    "CIITSymbolBorderRect", "CODMultiLineComp", "CIITArcComp", "CODPolygonComp",
    "CODLineComp", "CIITPinSymbolComp", "CIITPinConnectorComp",
    "CIITPinSymTextCompName", "CIITPinSymTextCompNumber",
}


def dedupe(src, dst):
    xml, _ = dcl.read_ms14(src)
    head = b""
    body = xml
    if xml.startswith(b"<?xml"):
        end = xml.find(b"?>")
        head = xml[:end + 2] + b"\n"
        body = xml[end + 2:]
    root = ET.fromstring(body)

    used = set()
    for e in root.iter():
        i = e.get("ID")
        if i and i.isdigit():
            used.add(int(i))
    state = [max(used) + 8 if used else 8]

    def new_id():
        v = state[0]
        while v in used:
            v += 8
        used.add(v)
        state[0] = v + 8
        return str(v)

    changed = 0
    for item in root.iter("Item"):
        if item.get("Class") != "CIITSymbolComp":
            continue
        # ConnectList 里的 Item 是 CODPinComp 定义引用，由 pin_map 统一处理，不能改
        protected = set()
        for cl in item.iter("ConnectList"):
            for it in cl.findall("Item"):
                protected.add(it)

        idmap = {}
        for el in item.iter("Item"):
            if el is item or el in protected:
                continue
            old = el.get("ID")
            if old and old.isdigit() and old not in idmap:
                idmap[old] = new_id()

        for el in item.iter("Item"):
            if el is item or el in protected:
                continue
            old = el.get("ID")
            if old in idmap:
                el.set("ID", idmap[old])
                changed += 1

    out = ET.tostring(root, encoding="ascii")
    if not out.startswith(b"<?xml") and head:
        out = head + out
    dcl.write_ms14(dst, out)
    return changed


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    n = dedupe(sys.argv[1], sys.argv[2])
    print("reassigned %d sub-object ids -> %s" % (n, sys.argv[2]))
