# -*- coding: utf-8 -*-
"""P11 收尾：给三份 JSON 补 note；复核 acceptance 的 PortID 绑定。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

NOTES = {
    "p11_a.json": ("A = p10 基底 + Assembler.add() 原样克隆的 V2（修复前）。失败，"
                   "现象与 acceptance 完全一致。",
                   "CIITPinSymbolComp@PortID 未重映射：克隆符号仍指向 donor 旧端口 CiID "
                   "(737288600/737288440)，目标文件里没有这些对象 -> 引脚符号与电气端口脱钩。",
                   "out/p11_a_fixed.json（同一实验，add() 修复后重建，通过）"),
    "p11_b.json": ("B = acceptance 基底 + donor_spice 原 V2 对象（PortID 按新端口重映射，"
                   "Attributes/CiModel 逐字保留）。通过。", None, None),
    "p11_final.json": ("最终 acceptance（msbuild.Assembler.add 修复 PortID 后重建）：通过。",
                       None, None),
}

for fn, (note, cause, see) in NOTES.items():
    p = os.path.join(ROOT, "out", fn)
    d = json.load(open(p, encoding="utf-8"))
    d["note"] = note
    if cause:
        d["root_cause"] = cause
    if see:
        d["see_also"] = see
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("updated", fn)

print()
print("=== acceptance 的引脚符号 -> 端口 绑定复核 ===")
c = msmodel.Circuit.load(os.path.join(ROOT, "out", "ref", "acceptance.ms14"))
for ref in ("V1", "R1", "C1"):
    ciid = c.find(ref)["ciid"]
    ports = {p["name"]: p["ciid"] for p in c.ports() if p["component"] == ciid}
    sym = c.symbol_of(ciid)
    hits = []
    for el in sym.iter():
        for k, v in el.attrib.items():
            if v in ports.values():
                hits.append((el.tag, k, v))
    print("  %-3s 端口=%s 绑定命中=%d %s" % (ref, ports, len(hits), hits))
