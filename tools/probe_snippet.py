# -*- coding: utf-8 -*-
"""Snippet 导出格式探测：如果 snippet 是不压缩的 XML，就等于拿到了电路文件的结构。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

with Multisim() as ms:
    c = ms.open(os.path.join(ROOT, "samples", "7812.ms12"))
    for name, fn in [
        ("snippet.ewsnip", lambda p: c._c.CreateSnippet(p, False, 1.0)),
        ("design.ewsnip", lambda p: c._c.SaveDesignAsSnippet(p, 1.0)),
    ]:
        p = os.path.join(OUT, name)
        try:
            r = fn(p)
            size = os.path.getsize(p) if os.path.exists(p) else -1
            head = open(p, "rb").read(64) if size > 0 else b""
            print("%-16s -> ok size=%-7d head=%r" % (name, size, head[:48]))
        except Exception as e:
            print("%-16s -> ERR %s" % (name, str(e)[:200]))
