# -*- coding: utf-8 -*-
"""只读：解包 docx，打印段落与表格结构（不修改任何东西）。"""
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = NS["w"]
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def text_of(el):
    return "".join(t.text or "" for t in el.iter("{%s}t" % W))


def dump(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find("w:body", NS)

    ti = 0
    pi = 0
    for child in body:
        tag = child.tag.split("}")[1]
        if tag == "p":
            s = text_of(child).strip()
            img = child.find(".//{%s}blip" % A) is not None
            if s or img:
                print("[P%02d] %s%s" % (pi, s, "  [图]" if img else ""))
            pi += 1
        elif tag == "tbl":
            print("\n===== TABLE %d =====" % ti)
            for ri, tr in enumerate(child.findall("w:tr", NS)):
                cells = []
                for tc in tr.findall("w:tc", NS):
                    cells.append(repr(text_of(tc).strip()))
                print("  row%d (%d cells): %s"
                      % (ri, len(cells), " | ".join(cells)))
            print("===== END TABLE %d =====\n" % ti)
            ti += 1


if __name__ == "__main__":
    dump(sys.argv[1] if len(sys.argv) > 1
         else r"C:\Users\A377\Downloads\1单元作业 (1).docx")
