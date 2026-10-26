# -*- coding: utf-8 -*-
"""P19-3：探针唯一命名隔离实验。

只做一件事：往 acceptance_divider.ms14（已有 1 个探针，读得出 V(探针1)）
再加第 2 个探针，落在源网 net1 的导线顶点 (493,300)，并把新探针的
CiProbeExtComp@LocalName 改成序号 2。

目的：验证「LocalName 序号唯一 → COM EnumOutputs 能区分两个输出」这个假设。
不改任何其他机制（不改元件、不改连线、不改仿真设置）。

产物：out/p19_two_probes.ms14
用法：python tools/p19_probe2.py
"""
import copy
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402

SRC = os.path.join(ROOT, "out", "ref", "acceptance_divider.ms14")
OUT = os.path.join(ROOT, "out", "p19_two_probes.ms14")
NEW_XY = (493.0, 300.0)     # net1 导线拐点（顶点）


def probe_name(base_local, idx):
    """&UNI_uc263a294881 + 2 -> &UNI_uc263a294882

    规则（实测自 RefDes 管理器）：LocalName = IRPrefix + IRNumber。
    donor 的 IRPrefix 是 &UNI_uc263a29488，序号是最后一位。
    """
    s = base_local or ""
    stem = s[:-1] if s and s[-1].isdigit() else s
    return "%s%d" % (stem, idx)


c = msmodel.Circuit.load(SRC)

draw = None
for e in c.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITProbeExtComponent":
        draw = e
        break
elec = None
for e in c.elements:
    if e.get("Class") == "CiProbeExtComp":
        elec = e
        break
if draw is None or elec is None:
    raise SystemExit("源文件里没有探针")

old_draw_id = draw.get("ID")
old_elec_id = elec.get("CiID")
print("donor 探针: draw=%s elec=%s LocalName=%s"
      % (old_draw_id, old_elec_id, elec.find("CiProbeExtComp").get("LocalName")))

# ---- 绘图对象 ----
new_draw = copy.deepcopy(draw)
new_draw_id = c.new_id()
new_draw.set("ID", new_draw_id)
ndi = list(new_draw)[0]
ndi.set("Transformer-M20", "%g" % NEW_XY[0])
ndi.set("Transformer-M21", "%g" % NEW_XY[1])

# ---- 电气对象 ----
new_elec = copy.deepcopy(elec)
new_elec_id = c.new_id()
new_elec.set("CiID", new_elec_id)
nei = list(new_elec)[0]
nei.set("SymCompID", new_draw_id)
nei.set("Circuit", elec.find("CiProbeExtComp").get("Circuit"))
old_local = nei.get("LocalName")
nei.set("LocalName", probe_name(old_local, 2))

ndi.set("CiProbeExtComp", new_elec_id)

# ---- 子树内旧 ID 全量重映射（COMPHANDLE_EXT 等）----
for tree in (new_draw, new_elec):
    for el in tree.iter():
        for k, v in list(el.attrib.items()):
            if v == old_draw_id:
                el.set(k, new_draw_id)
            elif v == old_elec_id:
                el.set(k, new_elec_id)

c.objects.append(new_draw)
c.elements.append(new_elec)

# ---- 注册进 CiCircuit/ProbeExts ----
ci = c.circuit_item.find("CiCircuit")
pe = ci.find("ProbeExts")
if pe is None:
    pe = ET.SubElement(ci, "ProbeExts")
it = ET.SubElement(pe, "Item")
it.set("CiID", new_elec_id)

n, _ = c.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))

# ---- 回读自检 ----
back = msmodel.Circuit.load(OUT)
names = []
for e in back.elements:
    if e.get("Class") == "CiProbeExtComp":
        names.append((e.get("CiID"), e.find("CiProbeExtComp").get("LocalName")))
print("探针数:", len(names))
for cid, nm in names:
    print("   CiID=%-12s LocalName=%s" % (cid, nm))
uniq = {nm for _, nm in names}
print("LocalName 唯一:", len(uniq) == len(names), "->", sorted(uniq))
for e in back.circuit_item.find("CiCircuit").find("ProbeExts"):
    print("   ProbeExts 注册:", e.get("CiID"))
