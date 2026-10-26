# -*- coding: utf-8 -*-
"""探测 Multisim 各种 Report* 的返回格式，找出哪种带元件值。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

CIRCUIT = os.path.join(ROOT, "out", "ref", "with_probes.ms14")


def show(tag, txt, limit=2200):
    print("\n" + "#" * 60)
    print("### %s  (len=%s)" % (tag, len(txt) if txt else "None"))
    print("#" * 60)
    if not txt:
        return
    for ln in txt.splitlines()[:40]:
        print("  | " + ln)
    if len(txt) > limit:
        print("  ... (截断)")


ms = msc.Multisim()
ms.connect()
c = ms.open(CIRCUIT)
print("opened:", c)

for tag, fn in (
    ("ReportNetlist text, with_probes=True", lambda: c.netlist(True, msc.ExportFmt.Text, None)),
    ("ReportNetlist text, with_probes=False", lambda: c.netlist(False, msc.ExportFmt.Text, None)),
    ("ReportNetlist CSV, with_probes=True", lambda: c.netlist(True, msc.ExportFmt.CSV, None)),
    ("ReportNetlist CSV, with_probes=False", lambda: c.netlist(False, msc.ExportFmt.CSV, None)),
    ("ReportBOM text, real_only=False", lambda: c.bom(False, msc.ExportFmt.Text, None)),
    ("ReportBOM text, real_only=True", lambda: c.bom(True, msc.ExportFmt.Text, None)),
    ("ReportBOM CSV, real_only=False", lambda: c.bom(False, msc.ExportFmt.CSV, None)),
):
    try:
        show(tag, fn())
    except Exception as e:
        print("\n### %s -> 失败 %r" % (tag, e))

print("\nDONE-PROBE")
# 故意不 Disconnect：实测 Disconnect 在打开过文件 + 跑过 Report 后会段错误
os._exit(0)
