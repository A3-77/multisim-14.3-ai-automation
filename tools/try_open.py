# -*- coding: utf-8 -*-
"""单独进程里尝试打开一个文件（崩溃不影响外层）。用法: python try_open.py <file>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

path = sys.argv[1]
try:
    with Multisim() as ms:
        c = ms.open(path)
        comps = c.components()
        print("OK|%s|%d" % (c.name, len(comps)))
        print("COMPS|" + ",".join(comps))
except Exception as e:
    print("FAIL|" + str(e).replace("\n", " ")[:300])
