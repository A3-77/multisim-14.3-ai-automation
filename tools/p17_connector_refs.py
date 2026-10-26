# -*- coding: utf-8 -*-
"""P17: 确认 CIITPinConnectorComp 在官方文件里由谁引用（符号内部 vs 引脚定义）。

用法: runtime\py32\python.exe tools\p17_connector_refs.py <ms14>
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

c = msmodel.Circuit.load(sys.argv[1])

# 找出所有 CIITPinConnectorComp 的定义 ID
conn_ids = set()
for e in c.tree.iter("Item"):
    if e.get("Class") == "CIITPinConnectorComp" and len(list(e)):
        conn_ids.add(e.get("ID"))
print("CIITPinConnectorComp 定义数:", len(conn_ids))

# 谁引用了它们
stat = Counter()
for e in c.tree.iter():
    if e.tag != "Item":
        continue
    for it in e.findall("ConnectList/Item"):
        if it.get("ID") in conn_ids:
            stat[e.get("Class")] += 1
            break
print("引用它们的父对象类:", dict(stat))

# CODPinComp 定义里 ConnectList 指向类的总分布
stat2 = Counter()
for e in c.tree.iter("Item"):
    if e.get("Class") != "CODPinComp" or not len(list(e)):
        continue
    cl = e.find("ConnectList")
    if cl is None:
        stat2["<无>"] += 1
        continue
    kinds = tuple(sorted({i.get("Class") for i in cl.findall("Item")}))
    stat2[",".join(kinds) or "<空>"] += 1
print("CODPinComp(定义) 的 ConnectList 指向类分布:", dict(stat2))
