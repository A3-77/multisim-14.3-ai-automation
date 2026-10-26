# -*- coding: utf-8 -*-
"""P12 诊断4：双探针变体 —— in 节点和 out 节点各放一个探针。

判别：
  in=5V, out=0V  -> R1 克隆出来是开路的
  in=0V, out=0V  -> 源本身没输出（donor 的 DC_POWER 取值槽不对）
  in=5V, out=5V  -> 之前那次是探针绑错网

同时把 V1 换成 donor_spice 的原 V2（已知能出 5V），排除索引源的问题。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR

OUT = os.path.join(ROOT, "out", "p12_diag2probe.ms14")
DONOR_SPICE = os.path.join(ROOT, "out", "donor_spice.ms14")


def place(a, family, part, refdes, value, pin, target, **kw):
    ciid, _ = a.add_part(family, part, refdes, value=value, x=0.0, y=0.0, **kw)
    info = a.c.pin_info(ciid)
    x0, y0 = info[pin]["xy"]
    a.c.translate(ciid, target[0] - x0, target[1] - y0)
    info = a.c.pin_info(ciid)
    print("  %-3s 引脚=%s" % (refdes, {k: (round(v["xy"][0], 1), round(v["xy"][1], 1))
                                       for k, v in info.items()}))
    return ciid, info


a = msbuild.Assembler()
spice = msbuild.load_donor(DONOR_SPICE)

# 源用 donor_spice 的原 V2（排除索引源）
v1, vinfo = place(a, "POWER_SOURCES", "DC_POWER", "V1", 5.0, "1", (300.0, 300.0),
                  donor_path=spice, donor_refdes="V2")
# in 网走折线：R1.1 比 V1.1 低 40
r1, rinfo = place(a, "RESISTOR", "RESISTOR_VIRTUAL", "R1", 1000.0, "1", (520.0, 340.0))
# out 网走折线：C1.1 比 R1.2 低 45
c1, cinfo = place(a, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", 100e-9, "1", (680.0, 430.0))

gnds = [c for c in spice.components() if c["part"] == "GROUND"]
spice.set_refdes(gnds[0]["ciid"], "GNDA")
spice.set_refdes(gnds[3]["ciid"], "GNDC")
ga, _ = place(a, "POWER_SOURCES", "GROUND", "0", None, "1", (300.0, 420.0),
              donor_path=spice, donor_refdes="GNDA")
gc, _ = place(a, "POWER_SOURCES", "GROUND", "0", None, "1", (680.0, 500.0),
              donor_path=spice, donor_refdes="GNDC")

n_in = a.connect([(v1, "1"), (r1, "1")], name="in")
n_out = a.connect([(r1, "2"), (c1, "1")], name="out")
a.connect([(v1, "2"), (ga, "1")], name="0")
a.connect([(c1, "2"), (gc, "1")], name="0")
print("节点 in=%s out=%s" % (n_in, n_out))

# 单个探针：argv[1] = in|out（默认 out）
WHICH = (sys.argv[1] if len(sys.argv) > 1 else "out").lower()
p_in = (rinfo["1"]["xy"][0], vinfo["1"]["xy"][1])
p_out = (cinfo["1"]["xy"][0], rinfo["2"]["xy"][1])
target = p_in if WHICH == "in" else p_out
print("探针 %s 位置=%s" % (WHICH, target))
clone_probe_ext(a, PROBE_DONOR, *target)

n, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))
back = msmodel.Circuit.load(OUT)
for e in back.objects:
    inner = list(e)
    if inner and inner[0].get("Class") == "CIITLinkComp":
        lnk = inner[0]
        print("  wire Node=%s pts=%s" % (lnk.get("Node"),
              [(p.get("X"), p.get("Y")) for p in lnk.find("Points")]))
