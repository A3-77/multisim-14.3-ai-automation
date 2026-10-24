# -*- coding: utf-8 -*-
"""Can Multisim save/open plain XML? Try SaveAs with .xml and read back."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(OUT, exist_ok=True)

with Multisim() as ms:
    c = ms.new()
    for name in ("blank.xml", "blank.ewxml", "blank.ms14"):
        p = os.path.join(OUT, name)
        try:
            r = c.save_as(p)
            size = os.path.getsize(p) if os.path.exists(p) else -1
            head = open(p, "rb").read(80) if size > 0 else b""
            print("%-14s -> ok  size=%-7d head=%r" % (name, size, head[:60]))
        except Exception as e:
            print("%-14s -> ERR %s" % (name, str(e)[:160]))
