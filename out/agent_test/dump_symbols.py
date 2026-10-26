# -*- coding: utf-8 -*-
"""检查生成的 .ms14 里各元件的绘图元素是否完整（开发者排查，非 Agent 任务）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dcl      # noqa: E402
import mssafe   # noqa: E402
import xml.etree.ElementTree as ET   # noqa: E402

MS14 = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                    "agent_rc_500hz.ms14")


def main():
    xml, info = dcl.read_ms14(MS14)
    root = mssafe.parse(xml)

    # 找所有符号元件
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag != "CIITSymbolComp":
            continue
        name = el.get("Name") or el.get("name") or "?"
        ciid = el.get("CiID") or el.get("ciid")
        kids = [c.tag.split("}")[-1] for c in el]
        n_draw = sum(1 for k in kids if "Draw" in k or "Line" in k or "Rect" in k)
        print("%-6s CiID=%-10s 子元素 %d 个，绘图类 %d 个" % (name, ciid, len(kids), n_draw))
        print("        %s" % kids[:14])

    print("\n--- 顶层对象统计 ---")
    from collections import Counter
    cnt = Counter(el.tag.split("}")[-1] for el in root.iter())
    for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])[:25]:
        print("  %-32s %d" % (k, v))


if __name__ == "__main__":
    main()
