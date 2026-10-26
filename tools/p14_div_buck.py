# -*- coding: utf-8 -*-
"""P14n: 用 buck.ms14（原生可跑）当 donor 重建分压器，检验 donor_spice 的电阻模板是否本身有问题"""
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild
from build_acceptance import clone_probe_ext, PROBE_DONOR
from p13_build import place, attach

BUCK = r"C:\Users\A377\Downloads\multisim_simulations\aareyes96-multisim_simulations-daff854\buck.ms14"
OUT = os.path.join(ROOT, "out", "p14_div_buck.ms14")

a = msbuild.Assembler()
d = msbuild.load_donor(BUCK)

print("donor 元件:", [c["refdes"] for c in d.components()])
gnds = [c for c in d.components() if c["part"] == "GROUND"]
d.set_refdes(gnds[0]["ciid"], "GNDA")

v1, vinfo = place(a, "V1", (300.0, 300.0), donor=d, donor_ref="V2", value=5.0)
r1, rinfo = place(a, "R1", (500.0, 340.0), donor=d, donor_ref="R1", value=1000.0)
r2, r2info = place(a, "R2", (650.0, 430.0), donor=d, donor_ref="R3", value=1000.0)
print("V1", {k: v["xy"] for k, v in vinfo.items()})
print("R1", {k: v["xy"] for k, v in rinfo.items()})
print("R2", {k: v["xy"] for k, v in r2info.items()})

n_in = a.connect([(v1, "1"), (r1, "1")], name="1")
n_mid = a.connect([(r1, "2"), (r2, "1")], name="2")
a.wire(n_mid, (r1, "2"), (r2, "1"))

c1, _ = a.add(msbuild.Donor(msbuild.load_donor(os.path.join(ROOT, "out", "donor_spice.ms14")), "C1"),
              x=790.0, y=430.0, refdes="C1")
a.c.set_value_by_refdes("C1", 1e-12)
cinfo = a.c.pin_info(c1)
print("C1", {k: v["xy"] for k, v in cinfo.items()})
attach(a, c1, "1", n_mid)
a.wire(n_mid, (r2, "1"), (c1, "1"))

gc2, _ = place(a, "0", (790.0, 520.0), donor=d, donor_ref="GNDA")
a.connect([(c1, "2"), (gc2, "1")], name="0")
gc, _ = place(a, "0", (650.0, 520.0), donor=d, donor_ref="GNDA")
a.connect([(r2, "2"), (gc, "1")], name="0")
ga, _ = place(a, "0", (300.0, 430.0), donor=d, donor_ref="GNDA")
a.connect([(v1, "2"), (ga, "1")], name="0")

clone_probe_ext(a, PROBE_DONOR, 650.0, 385.0)
n, _ = a.save(OUT)
print("写出 %s (%d 字节)" % (OUT, n))

back = msmodel.Circuit.load(OUT)
pm = {p["ciid"]: p for p in back.ports()}
for nd in back.nodes():
    names = []
    for pid in nd["ports"]:
        p = pm.get(pid)
        if p:
            ref = next((x["refdes"] for x in back.components() if x["ciid"] == p["component"]), "?")
            names.append("%s.%s" % (ref, p["name"]))
    print("  node %-10s ports=%s" % (nd["ciid"], names))
