# -*- coding: utf-8 -*-
"""检查 wave_p*.csv 的行列完整性与数值走向。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "hw1")

for pct in (10, 20, 100):
    p = os.path.join(OUT, "wave_p%d.csv" % pct)
    with open(p, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    head = lines[0]
    body = lines[1:]
    from collections import Counter
    cnt = Counter(len(ln.split(",")) for ln in body)
    print("=== p%d  head=%s  行数=%d  字段数分布=%s"
          % (pct, head, len(body), dict(cnt)))
    # 打印若干采样点
    for frac in (0.0, 0.05, 0.2, 0.5, 0.8, 0.95, 0.99, 1.0):
        i = min(len(body) - 1, int(frac * (len(body) - 1)))
        print("   [%5.1f%%] idx=%-6d %s" % (frac * 100, i, body[i]))
    print()
