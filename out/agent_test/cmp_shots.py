# -*- coding: utf-8 -*-
"""对比：原生样例 vs 我们生成的电路，GetCircuitImage 是否都缺符号。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import msc   # noqa: E402

DIR = os.path.join(ROOT, "out", "agent_test")
CASES = [
    ("native_r", os.path.join(ROOT, "corpus", "samples14",
                              "Amplificador para resistencia de 1mOhm.ms14")),
    ("native_555", os.path.join(ROOT, "corpus", "samples14",
                                "nivel de agua con 555.ms14")),
    ("gen_rc", os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                            "agent_rc_500hz.ms14")),
]


def main():
    for tag, path in CASES:
        if not os.path.isfile(path):
            print("%-10s 跳过（不存在）" % tag)
            continue
        try:
            ms = msc.Multisim()
            circ = ms.open(path)
            comps = circ.components()
            out = os.path.join(DIR, "cmp_%s.png" % tag)
            circ.snapshot(out)
            n = os.path.getsize(out)
            print("%-10s comps=%-3d 截图=%d 字节  %s"
                  % (tag, len(comps), n, comps[:6]))
            try:
                circ.stop()
            except Exception:
                pass
        except Exception as e:
            print("%-10s 失败：%s" % (tag, e))
        time.sleep(1.0)


if __name__ == "__main__":
    main()
