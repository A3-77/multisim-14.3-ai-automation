# -*- coding: utf-8 -*-
"""生成发布素材：Multisim 电路截图（必须 32 位 Python 跑）。

这不是 Agent 任务的一部分 —— Agent 任务已经通过 MCP 完成，
这个脚本只是把那次任务产出的 .ms14 截成图，放进 release。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import msc   # noqa: E402

MS14 = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                    "agent_rc_500hz.ms14")
OUT = os.path.join(ROOT, "docs", "case", "agent_rc_500hz_circuit.png")


def main():
    print("打开 %s" % MS14)
    ms = msc.Multisim()
    circ = ms.open(MS14)
    print("  probes = %s" % (circ.probes(),))
    print("  comps  = %s" % (circ.components(),))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    r = circ.snapshot(OUT)
    print("  截图 -> %s  (ret=%r)" % (OUT, r))
    try:
        circ.stop()
    except Exception:
        pass
    print("大小 %d 字节" % (os.path.getsize(OUT) if os.path.exists(OUT) else -1))


if __name__ == "__main__":
    main()
