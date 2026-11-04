# -*- coding: utf-8 -*-
"""核对 .ms14 的真实连通性：每个元件引脚落在哪个 CiNode，有没有悬空的。

Multisim 的连通性来自 CiNode/Ports 引用，跟画面上画了什么线无关 ——
所以「图上看着少根线」和「电气上真的没连」是两回事，必须分开判断。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msmodel  # noqa: E402


def report(path):
    c = msmodel.Circuit.load(path)
    ports = {p["ciid"]: p for p in c.ports()}
    nodes = c.nodes()

    # 端口 ciid -> 元件 ciid
    port2comp = {}
    for pid, p in ports.items():
        port2comp[pid] = p["component"]

    comp_name = {}
    for item in c.components():
        comp_name[item["ciid"]] = item["refdes"]

    print("=== %s" % os.path.basename(path))
    print("元件 %d 个，引脚 %d 个，网络 %d 个"
          % (len(comp_name), len(ports), len(nodes)))

    in_node = set()
    for n in nodes:
        members = []
        for pid in n["ports"]:
            in_node.add(pid)
            p = ports.get(pid)
            if not p:
                members.append("?%s" % pid)
                continue
            comp = comp_name.get(p["component"], p["component"])
            members.append("%s.%s" % (comp, p["name"]))
        print("  net %-6s : %s" % (n["name"] or "(unnamed)", ", ".join(members)))

    dangling = []
    for pid, p in ports.items():
        if pid in in_node:
            continue
        comp = comp_name.get(p["component"], p["component"])
        dangling.append("%s.%s" % (comp, p["name"]))
    if dangling:
        print("  !! 悬空引脚: %s" % ", ".join(sorted(dangling)))
    else:
        print("  没有悬空引脚")
    return dangling


if __name__ == "__main__":
    for p in sys.argv[1:]:
        report(p)
        print()
