# -*- coding: utf-8 -*-
"""P14：试 ReportNetlist 的其它格式 + DoCommandLine，看能不能吐出 SPICE deck。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

SRC = os.path.join(ROOT, "out", "p13_a3.ms14")
OUT = os.path.join(ROOT, "out", "p14_spice_deck.txt")

subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

ms = msc.Multisim()
c = ms.open(SRC)
buf = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    buf.append(s)


for fmt in (0, 1, 2, 3, 4):
    for probes in (False, True):
        try:
            txt = c._c.ReportNetlist(bool(probes), int(fmt), None)
            txt = msc._fix(txt) or ""
            log("=== fmt=%d probes=%s len=%d ===" % (fmt, probes, len(txt)))
            log(txt[:1500])
        except Exception as e:
            log("=== fmt=%d probes=%s 失败 %r ===" % (fmt, probes, e))

# 试着让它导出到文件
for fmt in (2, 3):
    p = os.path.join(ROOT, "out", "p14_net_fmt%d.txt" % fmt)
    try:
        c._c.ReportNetlist(False, int(fmt), p)
        ok = os.path.exists(p)
        log("fmt=%d 写文件 %s -> %s" % (fmt, p, ok))
        if ok:
            log(open(p, encoding="utf-8", errors="replace").read()[:1500])
    except Exception as e:
        log("fmt=%d 写文件失败 %r" % (fmt, e))

for cmd in ("netlist", "show netlist", "op"):
    try:
        r = c._c.DoCommandLine(cmd)
        log("DoCommandLine(%r) -> %r" % (cmd, r))
    except Exception as e:
        log("DoCommandLine(%r) 失败 %r" % (cmd, e))

open(OUT, "w", encoding="utf-8").write("\n".join(buf))
print("\n已写", OUT)
sys.stdout.flush()
os._exit(0)
