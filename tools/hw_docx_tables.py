# -*- coding: utf-8 -*-
"""检查 docx 里每张表的每个单元格：有文字就打印文字，有图就标 [图]。"""
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def cell_desc(tc):
    txt = "".join(t.text or "" for t in tc.iter("{%s}t" % W)).strip()
    has_img = tc.find(".//{%s}blip" % A) is not None
    parts = []
    if txt:
        parts.append(txt)
    if has_img:
        parts.append("[图]")
    return " ".join(parts) if parts else "·"


def main(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find("w:body", NS)
    ti = 0
    for tbl in body.iter("{%s}tbl" % W):
        print("===== TABLE %d =====" % ti)
        for ri, tr in enumerate(tbl.findall("w:tr", NS)):
            cells = [cell_desc(tc) for tc in tr.findall("w:tc", NS)]
            print("  row%d: %s" % (ri + 1, " | ".join(cells)))
        ti += 1


if __name__ == "__main__":
    main(sys.argv[1])
