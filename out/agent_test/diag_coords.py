# -*- coding: utf-8 -*-
"""诊断：生成电路里 V1 / C1 的绘图对象坐标是否还在 donor 的原始位置。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dcl      # noqa: E402
import mssafe   # noqa: E402

MS14 = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                    "agent_rc_500hz.ms14")
NATIVE = os.path.join(ROOT, "corpus", "samples14",
                      "Amplificador para resistencia de 1mOhm.ms14")


def walk(el, depth=0, out=None):
    if out is None:
        out = []
    tag = el.tag.split("}")[-1]
    out.append((depth, tag, dict(el.attrib)))
    for c in el:
        walk(c, depth + 1, out)
    return out


def scan(path, want):
    xml, info = dcl.read_ms14(path)
    root = mssafe.parse(xml)
    print("\n=== %s" % os.path.basename(path))
    for sym in root.iter():
        if sym.tag.split("}")[-1] != "CIITSymbolComp":
            continue
        # 找这个符号下的位号：通常是某个 CiaCString 值
        flat = walk(sym)
        texts = [a.get("Text") or a.get("text") or a.get("Value")
                 for _d, t, a in flat]
        texts = [t for t in texts if t]
        # 收集 Point 坐标
        pts = []
        for _d, t, a in flat:
            if t == "Point":
                x = a.get("X") or a.get("x")
                y = a.get("Y") or a.get("y")
                if x is not None and y is not None:
                    pts.append((float(x), float(y)))
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        label = [t for t in texts if t in want] or texts[:2]
        if not any(t in want for t in texts):
            continue
        print("  位号候选=%-18s 点数=%-3d x=[%.1f, %.1f] y=[%.1f, %.1f]"
              % (str(label), len(pts), min(xs), max(xs), min(ys), max(ys)))


if __name__ == "__main__":
    scan(MS14, {"V1", "R1", "C1"})
    scan(NATIVE, {"V1", "R1", "R2"})
