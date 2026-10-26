# -*- coding: utf-8 -*-
"""P15：验证「RefDes 注册缺失 → SPICE 丢元件」假设。

同一个分压器电路，唯一变量是克隆重元件时是否补 RefDes 注册：

  --refdes yes   新行为（add() 里自动登记 RefDesInfo）
  --refdes no    旧行为（跟 p13_a2 等价，做严格对照）

电路：V1=5V -- R1=1k -- 中点 -- R2=1k -- GND，中点再跨 1pF 到地，探针在中点。
期望中点 2.5V。

用法：
  python tools/p15_build.py --refdes yes --out p15_refdes_yes.ms14
  python tools/p15_build.py --refdes no  --out p15_refdes_no.ms14
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")


def place(a, refdes, target, pin="1", donor=None, donor_ref=None, value=None):
    ciid, _ = a.add_part("X", "Y", refdes, value=value, x=0.0, y=0.0,
                         donor_path=donor, donor_refdes=donor_ref)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    return ciid, a.c.pin_info(ciid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refdes", choices=("yes", "no"), default="yes")
    ap.add_argument("--cap", type=float, default=1e-12)
    ap.add_argument("--donor", default=None,
                    help="donor 文件路径；不给就用 out/donor_spice.ms14")
    ap.add_argument("--r-ref", default="R1", help="donor 里当电阻模板的位号")
    ap.add_argument("--c-ref", default="C1", help="donor 里当电容模板的位号")
    ap.add_argument("--v-ref", default="V2", help="donor 里当电压源模板的位号")
    ap.add_argument("--probe", choices=("ext", "old"), default="ext",
                    help="ext=新式 ProbeExt（几何绑定）; old=老式探针（显式 NetName）")
    ap.add_argument("--out", default="p15_build.ms14")
    args = ap.parse_args()

    msbuild.REGISTER_REFDES = (args.refdes == "yes")
    donor_path = args.donor or SPICE

    a = msbuild.Assembler()
    d = msbuild.load_donor(donor_path)
    gnds = [c for c in d.components() if c["part"] == "GROUND"]
    if len(gnds) < 2:
        raise RuntimeError("donor 里地符号不足 2 个：%s" % donor_path)
    d.set_refdes(gnds[0]["ciid"], "GNDA")
    d.set_refdes(gnds[-1]["ciid"], "GNDC")
    print("  donor = %s" % donor_path)

    v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref=args.v_ref, value=5.0)
    r1, rinfo = place(a, "R1", (500.0, 340.0), donor=d, donor_ref=args.r_ref, value=1000.0)
    r2, r2info = place(a, "R2", (650.0, 430.0), donor=d, donor_ref=args.r_ref, value=1000.0)
    c1, cinfo = place(a, "C1", (790.0, 430.0), donor=d, donor_ref=args.c_ref, value=args.cap)

    n_in = a.connect([(v1, "1"), (r1, "1")], name="1")
    n_mid = a.connect([(r1, "2"), (r2, "1")], name="2")
    a.wire(n_mid, (r1, "2"), (r2, "1"))
    # C1 挂在同一个中点网上
    p = next(x for x in a.c.ports() if x["component"] == c1 and x["name"] == "1")
    import xml.etree.ElementTree as ET
    nd = p["port"].find("Nodes")
    if nd is None:
        nd = ET.SubElement(p["port"], "Nodes")
    ET.SubElement(nd, "Item").set("CiID", n_mid)
    for e in a.c.elements:
        if e.get("CiID") == n_mid:
            ET.SubElement(e.find("CiNode/Ports"), "Item").set("CiID", p["ciid"])
    a.wire(n_mid, (r2, "1"), (c1, "1"))

    # 地：R2.2 / C1.2 / 地符号 必须落在同一个节点里（分两次 connect 会把
    # C1.2 同时挂到两个节点上，等于把电容短路掉）
    g1, _ = place(a, "0", (790.0, 520.0), donor=d, donor_ref="GNDC")
    n_g2 = a.connect([(r2, "2"), (c1, "2"), (g1, "1")], name="0")
    ga, _ = place(a, "0", (300.0, 430.0), donor=d, donor_ref="GNDA")
    a.connect([(v1, "2"), (ga, "1")], name="0")
    probe_xy = (650.0, rinfo["2"]["xy"][1])
    if args.probe == "old":
        # 老式探针：显式 NetName 绑网，不靠几何就近
        a.add_probe("2", probe_xy[0], probe_xy[1], name="MID")
        print("  老式探针 @ (%g,%g) 绑 net='2'" % probe_xy)
    else:
        clone_probe_ext(a, PROBE_DONOR, *probe_xy)
        print("  探针 @ (%g,%g)  中点节点=%s" % (probe_xy[0], probe_xy[1], n_mid))

    out = os.path.join(ROOT, "out", args.out)
    n, _ = a.save(out)
    print("写出 %s (%d 字节)  RefDes 登记=%s 条 %s"
          % (out, n, len(a.refdes_registered), a.refdes_registered))

    back = msmodel.Circuit.load(out)
    pm = {p["ciid"]: p for p in back.ports()}
    for nd2 in back.nodes():
        names = []
        for pid in nd2["ports"]:
            pp = pm.get(pid)
            if pp:
                ref = next((x["refdes"] for x in back.components()
                            if x["ciid"] == pp["component"]), "?")
                names.append("%s.%s" % (ref, pp["name"]))
        print("  node %-10s name=%-3r ports=%s" % (nd2["ciid"], nd2["name"], names))
    ext = msbuild.refdes_extension(back)
    cont = msbuild._refdes_container(back)
    items = cont.findall("CIRToInfoMap/CIRToInfoMapItem") if cont is not None else []
    print("  回读 RefDes 条目: %d 个 %s" % (len(items), [i.get("CIRKey") for i in items]))
    for i in items:
        print("     %s" % i.find("RefDesInfo/RefDesInfoData").get("RefDes"))


if __name__ == "__main__":
    main()
