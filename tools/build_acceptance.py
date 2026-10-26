# -*- coding: utf-8 -*-
"""固化验收电路：V1(5V) + R1(1kΩ) + GND×2 + C1(1pF) + 新式 ProbeExt。

配方来源：p10_probe.ms14 实证跑通（COM EnumOutputs 非空、transient 读出恒定 5.0V）。
本脚本把该配方固化为可重复执行的一条命令，不再重新探索。

拓扑（等电位意义）：
    net1: V1.1(+) --- R1.1 --- C1.1        （探针测这里，期望 5.0V）
    net0: V1.2(-) --- R1.2 --- C1.2 --- GND×2

关键经验（都来自实测，勿改）：
  1. **C1 不能省**：纯电阻回路（V+R+GND）瞬态在毫秒级算完，state 立刻回
     stopped、EnumOutputs 为空——和"引擎拒绝"表面现象完全一样（p5/p7 踩过）。
     有动态元件后仿真持续 running，output 才注册得上来（p8_dyn 100µF 实证）。
  2. **ProbeExt 绑网络靠位置**：CIITProbeExtComponent 的 Transformer-M20/M21
     必须精确落在目标网络导线的**一个顶点**上（线段中间、引脚端点都不行）。
     p10 的探针在 (720,297)，正是 net1 导线的拐点。
  3. **CiProbeExtComp 电气对象**：SymCompID → 绘图对象 ID，InstanceID 换新
     GUID，Circuit → 本电路 CiID；并在 CiCircuit/ProbeExts 注册 `<Item CiID=.. />`。
     绘图对象里 DefaultInstrumentProperties/COMPHANDLE_EXT 的 Data 要同步改成
     新绘图 ID（悬空引用会被 Multisim 静默丢弃）。
  4. 布局几何：V1(360,300)、R1(520,322) 时，net1 导线自动生成拐点 (513,300)，
     距 R1.1 18px、距 R1.2 63px——与 p10 同构（拐点位于 R1 两引脚之间，
     竖段不碰另一个引脚）。探针放 (513,300)。

用法：
    python tools/build_acceptance.py            # C1=1pF（默认）
    python tools/build_acceptance.py --cap 1e-4 # C1=100µF（p10 原值，兜底）

产物：out/ref/acceptance.ms14（覆盖前把旧文件备份为 out/ref/acceptance.noprobe.ms14）
"""
import os
import shutil
import sys
import copy
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gzip
import msmodel
import msbuild

DONOR = os.path.join(ROOT, "corpus", "samples",
                     "LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml.gz")
PROBE_DONOR = os.path.join(ROOT, "out", "ref", "with_probes.ms14")
OUT = os.path.join(ROOT, "out", "ref", "acceptance.ms14")
BACKUP = os.path.join(ROOT, "out", "ref", "acceptance.noprobe.ms14")

# 布局（引脚坐标由 pin_info 实测，见文件头注释）
POS = {"V1": (360.0, 300.0), "R1": (520.0, 322.0), "C1": (430.0, 400.0),
       "GND_A": (240.0, 360.0), "GND_C": (459.0, 404.0)}
PROBE_XY = (513.0, 300.0)     # net1 导线拐点（顶点）


def clone_probe_ext(a, donor_path, x, y):
    """把 donor 里的新式 ProbeExt（CIITProbeExtComponent + CiProbeExtComp +
    DefaultInstrumentProperties）克隆到 (x, y)，注册进 CiCircuit/ProbeExts。

    返回 (新电气 CiID, 新绘图 ID)。
    """
    donor = msmodel.Circuit.load(donor_path)

    draw = None
    for e in donor.objects:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITProbeExtComponent":
            draw = e
            break
    elec = None
    for e in donor.elements:
        if e.get("Class") == "CiProbeExtComp":
            elec = e
            break
    if draw is None or elec is None:
        raise RuntimeError("donor %s 里没有新式 ProbeExt" % donor_path)

    old_draw_id = draw.get("ID")
    old_elec_id = elec.get("CiID")

    # 1) 绘图对象：新 ID + 平移 + 回指新电气 CiID
    new_draw = copy.deepcopy(draw)
    new_draw_id = a.new_id()
    new_draw.set("ID", new_draw_id)
    ndi = list(new_draw)[0]
    ndi.set("Transformer-M20", "%g" % x)
    ndi.set("Transformer-M21", "%g" % y)

    # 2) 电气对象：新 CiID + SymCompID/InstanceID/Circuit
    new_elec = copy.deepcopy(elec)
    new_elec_id = a.new_id()
    new_elec.set("CiID", new_elec_id)
    nei = list(new_elec)[0]
    nei.set("SymCompID", new_draw_id)
    nei.set("InstanceID", msbuild._fresh_guid())
    nei.set("Circuit", a.circuit_ciid)

    # 3) 双向引用 + 子树内所有旧 ID 重映射（COMPHANDLE_EXT 等）
    ndi.set("CiProbeExtComp", new_elec_id)
    for el in new_draw.iter():
        for k, v in list(el.attrib.items()):
            if v == old_draw_id:
                el.set(k, new_draw_id)
            elif v == old_elec_id:
                el.set(k, new_elec_id)
    for el in new_elec.iter():
        for k, v in list(el.attrib.items()):
            if v == old_draw_id:
                el.set(k, new_draw_id)
            elif v == old_elec_id:
                el.set(k, new_elec_id)

    a.objs.append(new_draw)
    a.els.append(new_elec)

    # 4) 注册进 CiCircuit/ProbeExts
    pe = a.circuit_inner.find("ProbeExts")
    if pe is None:
        pe = ET.SubElement(a.circuit_inner, "ProbeExts")
    it = ET.SubElement(pe, "Item")
    it.set("CiID", new_elec_id)
    return new_elec_id, new_draw_id


def build_divider(args):
    """更强的验收：V1(5V) - R1(1k) - 中点 - R2(1k) - GND，探针在中点。

    为什么需要这个：上面的 acceptance.ms14 探针落在 net1（电源网），读出 5.0V
    只能证明电源在，**证明不了电阻导通**。中点读 2.5V 才是电阻真的在导通的证据。

    中点有 3 个引脚汇聚（R1.2 / R2.1 / C1.1），所以这里顺带验证了「T 型交汇
    不需要额外 junction 对象」——实测 2.5V。
    """
    donor = msmodel.Circuit(gzip.open(DONOR, "rb").read())
    a = msbuild.Assembler()

    v1, _ = a.add(msbuild.Donor(donor, "V2"), x=300.0, y=300.0, refdes="V1")
    a.c.set_value_by_refdes("V1", 5.0)
    r1, _ = a.add(msbuild.Donor(donor, "R1"), x=500.0, y=340.0, refdes="R1")
    a.c.set_value_by_refdes("R1", 1000.0)
    r2, _ = a.add(msbuild.Donor(donor, "R1"), x=650.0, y=430.0, refdes="R2")
    a.c.set_value_by_refdes("R2", 1000.0)
    c1, _ = a.add(msbuild.Donor(donor, "C1"), x=790.0, y=430.0, refdes="C1")
    a.c.set_value_by_refdes("C1", args.cap)

    gnds = [c for c in donor.components() if c["part"] == "GROUND"]
    donor.set_refdes(gnds[0]["ciid"], "GNDA")
    donor.set_refdes(gnds[3]["ciid"], "GNDC")

    n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
    n2 = a.connect([(r1, "2"), (r2, "1"), (c1, "1")], name="2")
    a.connect([(v1, "2"), (a.add(msbuild.Donor(donor, "GNDA"), x=300.0, y=470.0)[0], "1")],
              name="0")
    a.connect([(r2, "2"), (a.add(msbuild.Donor(donor, "GNDC"), x=650.0, y=540.0)[0], "1")],
              name="0")
    a.connect([(c1, "2"), (a.add(msbuild.Donor(donor, "GNDC"), x=790.0, y=540.0)[0], "1")],
              name="0")
    print("节点: net1=%s 中点=%s" % (n1, n2))

    # 探针落在中点导线的中间顶点
    vx = None
    for e in a.objs:
        inner = list(e)
        if inner and inner[0].get("Class") == "CIITLinkComp" and inner[0].get("Node") == n2:
            pts = [(float(p.get("X")), float(p.get("Y"))) for p in inner[0].find("Points")]
            vx = pts[1] if len(pts) >= 3 else pts[0]
            print("中点导线 pts=%s 探针落点=%s" % (pts, vx))
            break
    if vx is None:
        raise SystemExit("找不到中点导线")
    clone_probe_ext(a, PROBE_DONOR, vx[0], vx[1])

    out = os.path.join(ROOT, "out", "ref", "acceptance_divider.ms14")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n, _ = a.save(out)
    print("写出 %s (%d 字节)" % (out, n))
    back = msmodel.Circuit.load(out)
    pm = {p["ciid"]: p for p in back.ports()}
    for nd in back.nodes():
        names = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                ref = next((x["refdes"] for x in back.components()
                            if x["ciid"] == p["component"]), "?")
                names.append("%s.%s" % (ref, p["name"]))
        print("  node %-10s ports=%s" % (nd["ciid"], names))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=1e-12,
                    help="C1 容值（法拉），默认 1e-12（1pF）")
    ap.add_argument("--no-probe", action="store_true",
                    help="只搭电路不放探针（调试用）")
    ap.add_argument("--divider", action="store_true",
                    help="改搭分压器版本（中点应读 2.5V），产物 acceptance_divider.ms14")
    args = ap.parse_args()

    if args.divider:
        build_divider(args)
        return

    donor = msmodel.Circuit(gzip.open(DONOR, "rb").read())
    a = msbuild.Assembler()

    # 1) 元件
    v1, _ = a.add(msbuild.Donor(donor, "V2"), x=POS["V1"][0], y=POS["V1"][1],
                  refdes="V1")
    a.c.set_value_by_refdes("V1", 5.0)
    r1, _ = a.add(msbuild.Donor(donor, "R1"), x=POS["R1"][0], y=POS["R1"][1],
                  refdes="R1")
    a.c.set_value_by_refdes("R1", 1000.0)
    c1, _ = a.add(msbuild.Donor(donor, "C1"), x=POS["C1"][0], y=POS["C1"][1],
                  refdes="C1")
    a.c.set_value_by_refdes("C1", args.cap)
    # 两个 GND 必须克隆自**不同的** donor GND 元件：
    # donor 里 4 个 GND 共用 refdes "0"，Donor 按 refdes 只能取到第一个；
    # 若两个 GND 来自同一符号，引脚 def 的 ConnectList 会指向同一个连接器 ID，
    # 文件里出现重复对象 ID，Multisim 解析歧义会静默丢弃连线
    # （实测：V1.2—GND 断开 → 网络浮动 → 仿真无输出「输出未找到」）。
    # 先给 donor 的 GND 改唯一 refdes 才能分别选源（p10 用第 1 和第 4 个）。
    gnds = [c for c in donor.components() if c["part"] == "GROUND"]
    donor.set_refdes(gnds[0]["ciid"], "GNDA")
    donor.set_refdes(gnds[3]["ciid"], "GNDC")
    ga, _ = a.add(msbuild.Donor(donor, "GNDA"), x=POS["GND_A"][0], y=POS["GND_A"][1],
                  refdes="0")
    gc, _ = a.add(msbuild.Donor(donor, "GNDC"), x=POS["GND_C"][0], y=POS["GND_C"][1],
                  refdes="0")
    print("元件: V1=%s R1=%s C1=%s GND=%s/%s" % (v1, r1, c1, ga, gc))
    for tag, cid in (("V1", v1), ("R1", r1), ("C1", c1)):
        info = a.c.pin_info(cid)
        print("  %-3s 引脚: %s" % (tag, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                                          for k, v in info.items()}))

    # 2) 连线（net1 导线自动带拐点 (513,300)）
    n1 = a.connect([(v1, "1"), (r1, "1")], name="1")
    n0a = a.connect([(v1, "2"), (ga, "1")], name="0")
    n0c = a.connect([(r1, "2"), (gc, "1")], name="0")
    # C1 跨接回路两端（接 V1 引脚，等电位于跨接 R1；走 p10 实证路线）
    n5 = a.connect([(v1, "1"), (c1, "1")], name="5")
    n6 = a.connect([(c1, "2"), (v1, "2")], name="6")
    print("节点: net1=%s net0=%s/%s net5=%s net6=%s" % (n1, n0a, n0c, n5, n6))

    # 3) 探针（落在 net1 导线顶点）
    if not args.no_probe:
        elec_id, draw_id = clone_probe_ext(a, PROBE_DONOR, *PROBE_XY)
        print("ProbeExt: 电气=%s 绘图=%s 位置=%s" % (elec_id, draw_id, PROBE_XY))

    # 4) 备份 + 写出
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT) and not os.path.exists(BACKUP):
        shutil.copy2(OUT, BACKUP)
        print("已备份旧 acceptance.ms14 -> acceptance.noprobe.ms14")
    n, body = a.save(OUT)
    print("写出 %s (%d 字节)" % (OUT, n))

    # 5) 回读自检
    back = msmodel.Circuit.load(OUT)
    print("回读:", back.summary())
    wires = [e for e in back.objects
             if list(e) and list(e)[0].get("Class") == "CIITLinkComp"]
    for e in wires:
        lnk = list(e)[0]
        pts = [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]
        print("  wire %s Node=%s pts=%s" % (e.get("ID"), lnk.get("Node"), pts))
    pes = [e for e in back.objects
           if list(e) and list(e)[0].get("Class") == "CIITProbeExtComponent"]
    for e in pes:
        di = list(e)[0]
        print("  probe ID=%s M20/M21=%s/%s CiProbeExtComp=%s"
              % (e.get("ID"), di.get("Transformer-M20"), di.get("Transformer-M21"),
                 di.get("CiProbeExtComp")))
    for e in back.elements:
        if e.get("Class") == "CiCircuit":
            pe = list(e)[0].find("ProbeExts")
            print("  ProbeExts 注册:", [i.get("CiID") for i in pe] if pe is not None else None)
            break


if __name__ == "__main__":
    main()
