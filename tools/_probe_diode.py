# -*- coding: utf-8 -*-
"""三/二端新元件实验：二极管半波整流。

两件事：
  A. 走 MCP 走一遍，看 IR 层认不认 DIODE（预期：认不出，报结构化错误）
  B. 绕过 IR，直接用 msbuild + ir_sim 建一个二极管电路并真跑仿真
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msbuild      # noqa: E402
import ir_sim       # noqa: E402

PY = os.path.join(ROOT, "runtime", "py32", "python.exe")
CLI = os.path.join(ROOT, "tools", "agent_acceptance", "agent_cli.py")
WD = os.path.join(ROOT, "out", "probe_parts")


def mcp(tool, args):
    p = subprocess.run([PY, CLI, "--workdir", WD, "call", tool,
                        json.dumps(args, ensure_ascii=False)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(p.stdout)


print("=" * 70)
print("A. MCP 层：能不能 add_component 一个二极管？")
print("=" * 70)
cid = mcp("create_circuit", {"name": "diode_probe"})["circuit_id"]
for fam, part in (("DIODE", "1N4007G"), ("BJT_NPN", "2N2222A"), ("OPAMP", "LM358AD")):
    r = mcp("add_component", {"circuit_id": cid, "family": fam, "part": part,
                              "refdes": "X1"})
    err = r.get("error") or {}
    print("  %-10s %-10s -> ok=%s  %s" % (fam, part, r.get("ok"),
                                          (err.get("code", "") + " | " + err.get("message", ""))[:110]))
    if err.get("hint"):
        print("                hint: %s" % err["hint"][:150])
    if err.get("context"):
        print("                context: %s" % json.dumps(err["context"], ensure_ascii=False)[:200])

print("\n" + "=" * 70)
print("B. msbuild 层：直接建半波整流电路（V1 5V/50Hz -> D1 -> R1 -> GND）")
print("=" * 70)
a = msbuild.Assembler()
POS = {"V1": (300.0, 300.0), "D1": (520.0, 300.0), "R1": (740.0, 300.0), "GND": (740.0, 430.0)}

v1, _ = a.add_part("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1", value=5.0,
                   x=POS["V1"][0], y=POS["V1"][1])
print("  V1 ciid=%s 引脚=%s" % (v1, list(a.c.pin_info(v1))))

d1, _ = a.add_part("DIODE", "1N4007G", "D1", x=POS["D1"][0], y=POS["D1"][1])
print("  D1 ciid=%s 引脚=%s" % (d1, list(a.c.pin_info(d1))))

r1, _ = a.add_part("RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0,
                   x=POS["R1"][0], y=POS["R1"][1])
print("  R1 ciid=%s 引脚=%s" % (r1, list(a.c.pin_info(r1))))

gnd, _ = a.add_part("POWER_SOURCES", "GROUND", "0", x=POS["GND"][0], y=POS["GND"][1])
print("  GND ciid=%s 引脚=%s" % (gnd, list(a.c.pin_info(gnd))))

# V1 需要设置频率
try:
    a.c.set_value_by_refdes("V1", 5.0)
except Exception as e:
    print("  set_value V1:", e)

n_in = a.connect([(v1, "1"), (d1, "A")], name="in")
n_out = a.connect([(d1, "K"), (r1, "1")], name="out")
n_g = a.connect([(v1, "2"), (r1, "2"), (gnd, "1")], name="0")
print("  nets: in=%s out=%s 0=%s" % (n_in, n_out, n_g))


def pick(node_id):
    vs = a.net_vertices(node_id)
    if not vs:
        raise SystemExit("网络 %s 没有导线顶点" % node_id)
    return vs[1] if len(vs) >= 3 else vs[0]


xy_in, xy_out = pick(n_in), pick(n_out)
p1, _ = a.add_probe_ext(xy_in[0], xy_in[1], index=1)
p2, _ = a.add_probe_ext(xy_out[0], xy_out[1], index=2)
print("  探针: P1@in, P2@out")

outdir = os.path.join(ROOT, "out", "probe_parts")
os.makedirs(outdir, exist_ok=True)
ms14 = os.path.join(outdir, "diode_halfwave.ms14")
a.save(ms14)
print("  已保存: %s  (%d bytes)" % (ms14, os.path.getsize(ms14)))

print("\n  --- 重新读回来校验结构 ---")
c2 = msbuild.load_donor(ms14)
for d in c2.components():
    print("     %-4s %-24s %-20s pins=%s" % (d["refdes"], d["family"], d["part"],
                                             list(c2.pin_info(d["ciid"]))))

print("\n  --- 真机仿真 ---")
res = ir_sim.simulate(ms14, stop=0.05, sample_rate=200000.0, timeout=180.0, verbose=False)
print("  status=%s n=%s outputs=%s" % (res.get("status"), res.get("n"), res.get("outputs")))
data = res.get("data") or {}
for nm, (tt, vv) in data.items():
    if not vv:
        continue
    print("  %-14s n=%-6d min=%.4f max=%.4f mean=%.4f" % (nm, len(vv), min(vv), max(vv), sum(vv) / len(vv)))

with open(os.path.join(outdir, "diode_result.json"), "w", encoding="utf-8") as f:
    json.dump({"ms14": ms14, "status": res.get("status"), "n": res.get("n"),
               "outputs": res.get("outputs"),
               "summary": {k: {"min": min(v[1]), "max": max(v[1]),
                               "mean": sum(v[1]) / len(v[1]), "n": len(v[1])}
                           for k, v in data.items() if v[1]}},
              f, ensure_ascii=False, indent=2)
print("\n完成。")
