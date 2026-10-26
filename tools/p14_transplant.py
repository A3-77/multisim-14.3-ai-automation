# -*- coding: utf-8 -*-
"""P14d: 移植实验
A) p13_a3 里把克隆 R1 的 CiComponent 属性替换为 donor 原始 R1 的（保留新 CiID/端口/符号）
B) 对照组：原样 p13_a3
两次都跑 transient 读中点。
"""
import copy
import os
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import msmodel

SRC = os.path.join(ROOT, "out", "p13_a3.ms14")
DONOR = os.path.join(ROOT, "out", "donor_spice.ms14")
OUT = os.path.join(ROOT, "out", "p14_transplant.ms14")


def load_xml(path, tag):
    xml, _ = dcl.read_ms14(path)
    p = os.path.join(ROOT, "out", "_p14_%s.xml" % tag)
    open(p, "wb").write(xml)
    return p


src_xml = load_xml(SRC, "a3src")
don_xml = load_xml(DONOR, "donor2")

cs = msmodel.Circuit.from_xml_file(src_xml)
cd = msmodel.Circuit.from_xml_file(don_xml)

# 克隆 R1
c_ciid = cs.find("R1")["ciid"]
c_item = cs._item_of(c_ciid)
c_inner = c_item.find("CiComponent")

# donor R1
d_ciid = cd.find("R1")["ciid"]
d_item = cd._item_of(d_ciid)
d_inner = d_item.find("CiComponent")

print("克隆 R1 CiID=%s Circuit=%s SymCompID=%s" % (c_ciid, c_inner.get("Circuit"), c_inner.get("SymCompID")))
print("donor R1 CiID=%s Circuit=%s SymCompID=%s" % (d_ciid, d_inner.get("Circuit"), d_inner.get("SymCompID")))

# 电路 CiCircuit 的 CiID（保持克隆件所属电路）
circ_ciid = c_inner.get("Circuit")
sym_id = c_inner.get("SymCompID")
local_name = c_inner.get("LocalName")

# 用 donor 的 CiComponent 属性重建，但重映射归属
new_inner = copy.deepcopy(d_inner)
new_inner.set("Circuit", circ_ciid)
new_inner.set("SymCompID", sym_id)
new_inner.set("LocalName", local_name)
new_inner.set("InstanceID", "{%s}" % str(uuid.uuid4()).upper())

# 阻值改成 1k（donor 是 50）
pl = new_inner.find("Attributes")[2].find("CiaParamList")
nums = pl.find("doubles").findall("Item")
nums[1].set("Value", "1000.")
ps = pl.find("parameters").findall("Item")
ps[1].set("Value", "&ASC1k")

# 替换
c_item.remove(c_inner)
c_item.append(new_inner)

xml_out = ET.tostring(cs.tree, encoding="ascii", xml_declaration=True)
cs.save(OUT)
print("已保存:", OUT, os.path.getsize(OUT), "字节")
