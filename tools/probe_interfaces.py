# -*- coding: utf-8 -*-
"""1) 类型库里到底有几个接口/类 2) 界面字符串里有没有压缩/XML 开关"""
import os, re, glob
import comtypes.client as cc

DLL = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\MSInterface.dll"
m = cc.GetModule(DLL)
print("=== 类型库全部成员 ===")
names = [n for n in dir(m) if not n.startswith("_")]
for n in names:
    o = getattr(m, n)
    kind = type(o).__name__
    print("  %-32s %s" % (n, kind))

print("\n=== 界面字符串：compress / xml ===")
base = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\stringfiles\English"
for f in sorted(glob.glob(os.path.join(base, "*.ewstr"))):
    txt = open(f, encoding="utf-16", errors="ignore").read()
    for line in txt.splitlines():
        if re.search(r"compress|\.xml|XML", line, re.I):
            print("  %-22s %s" % (os.path.basename(f), line.strip()[:120]))
