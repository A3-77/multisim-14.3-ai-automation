# -*- coding: utf-8 -*-
"""扫描所有 Multisim 样例，建立"元件模板索引"。

对每个 .ms14：
  1. 解析容器头，用编译好的 dcltool.exe 解压（比纯 Python 快得多）
  2. 找到 CIITDiagram/Elements
  3. 把每个 CiComponent 的 family/part 提取出来
结果写 out/samples_index.json，并把解压后的 XML 缓存到 out/samples/
"""
import json
import os
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLES = r"C:\Users\Public\Documents\National Instruments\Circuit Design Suite 14.3\samples"
DCLTOOL = os.path.join(ROOT, "vendor", "dcltool.exe")
CACHE = os.path.join(ROOT, "out", "samples")
TMP = os.path.join(ROOT, "out", "_tmp.xml")
MAGIC_MSM = b"MSMCompressedElectronicsWorkbenchXML"
MAGIC_PLAIN = b"CompressedElectronicsWorkbenchXML"

os.makedirs(CACHE, exist_ok=True)


def body_offset(path):
    with open(path, "rb") as f:
        head = f.read(64)
    if head.startswith(MAGIC_MSM):
        return len(MAGIC_MSM)
    if head.startswith(MAGIC_PLAIN):
        return len(MAGIC_PLAIN)
    return None


def decompress(path):
    """按分块容器逐块解压（用编译版 dcltool，快）。"""
    with open(path, "rb") as f:
        d = f.read()
    off = body_offset(path)
    if off is None:
        return None
    total, zero, cu, cc = struct.unpack_from("<IIII", d, off)
    pos = off + 16
    parts = []
    while True:
        r = subprocess.run([DCLTOOL, "d", path, TMP, str(pos)], capture_output=True)
        if r.returncode != 0 or not os.path.exists(TMP):
            return None
        blob = open(TMP, "rb").read()
        if len(blob) != cu:
            return None
        parts.append(blob)
        pos += cc
        if pos >= len(d):
            break
        cu, cc = struct.unpack_from("<II", d, pos)
        pos += 8
    xml = b"".join(parts)
    return xml if len(xml) == total else None


def comp_identity(comp):
    """从 CiComponent 的 Attributes 里抽出 (family, part)。

    Multisim 把元件身份存成 CiaCollString，典型内容：
        ["POWER_SOURCES", "GROUND", "POWER_SOURCES", "EMPTY", "1", "Generic"]
        ["CAPACITOR", "CAPACITOR_VIRTUAL", "CAPACITOR", "VIRTUAL_CAPACITANCE", ...]
    取第一个"看起来像族名"的非空列表的前两项。
    """
    cands = []
    for it in comp.find("Attributes") or []:
        for cs in it.iter("CiaCollString"):
            vals = [(s.get("Value") or "").replace("&ASC", "")
                    for s in cs.iter("Item")]
            vals = [v for v in vals if v.strip()]
            if vals:
                cands.append(vals)
    for vals in cands:
        head = vals[0]
        if head and head == head.upper() and " " not in head:
            part = vals[1] if len(vals) > 1 else ""
            return head, part
    return (cands[0][0] if cands and cands[0] else ""), ""


def main():
    files = []
    for dirpath, _, names in os.walk(SAMPLES):
        for n in names:
            if n.lower().endswith(".ms14"):
                files.append(os.path.join(dirpath, n))
    files.sort()
    print("共 %d 个样例" % len(files), flush=True)

    index = []
    for i, p in enumerate(files):
        rel = os.path.relpath(p, SAMPLES)
        size = os.path.getsize(p)
        if size > 6_000_000:
            print("[%3d] 跳过(太大) %s" % (i, rel), flush=True)
            continue
        try:
            xml = decompress(p)
            if not xml:
                print("[%3d] 解压失败 %s" % (i, rel), flush=True)
                continue
            root = ET.fromstring(xml)
            els = root.find(".//CIITDiagram/Elements")
            if els is None:
                print("[%3d] 无 Elements %s" % (i, rel), flush=True)
                continue
            comps = []
            for e in els:
                if e.get("Class") == "CiComponent":
                    c = e.find("CiComponent")
                    if c is None:
                        continue
                    fam, part = comp_identity(c)
                    comps.append({"ciid": e.get("CiID"),
                                  "name": (c.get("LocalName") or "").replace("&ASC", ""),
                                  "family": fam, "part": part})
            cache = os.path.join(CACHE, rel.replace(os.sep, "__"))
            if os.path.exists(cache):
                os.remove(cache)
            os.replace(TMP, cache)
            index.append({"file": p, "rel": rel, "bytes": size,
                          "xml_bytes": len(xml), "cache": cache,
                          "components": comps})
            print("[%3d] %-58s %2d 元件  %s" % (
                i, rel[:58], len(comps),
                ", ".join(sorted({c["family"] or "?" for c in comps}))[:70]), flush=True)
        except Exception as e:
            print("[%3d] 异常 %s: %r" % (i, rel, e), flush=True)

    out = os.path.join(ROOT, "out", "samples_index.json")
    json.dump(index, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n索引已写入", out, "共", len(index), "项")


if __name__ == "__main__":
    main()
