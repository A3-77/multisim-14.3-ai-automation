# -*- coding: utf-8 -*-
"""P12：把诊断结论写进 out/ref/p12_rc.json。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = os.path.join(ROOT, "out", "ref", "p12_rc.json")

d = json.load(open(P, encoding="utf-8"))
d["note"] = ("RC 低通已生成、能打开、探针注册成功、2000 点数据回来了，"
             "但 Vout 恒 0，未呈 RC 充电曲线。卡点已定位到两个候选，见 diagnosis。")
d["diagnosis"] = {
    "netlist_ok": ("Multisim 连通性网表正确：node1=V1.1+R1.1，node2=R1.2+C1.1，"
                   "node0=V1.2+C1.2+GND×2"),
    "r1_identical_to_acceptance": ("rc_lowpass 的 R1 与 acceptance 的 R1 逐槽全等"
                                   "（47 槽、params 均为 ['0.','1000.','0.','0.','1.','27.']，"
                                   "仅 InstanceID 不同）"),
    "probe_on_source_net": "同构布局下探针放 in 网（V1.1+R1.1）读到 5.0V（V=5V 版本）",
    "probe_on_out_net": "探针放 out 网（R1.2+C1.1）读到 0.0V，2000 点全 0（V=1V 与 5V 都一样）",
    "pure_resistive_inconclusive": ("V1-R1-R2-GND 纯电阻分压器无动态元件，仿真秒停、"
                                    "报「输出未找到」（符合 docs/p0-acceptance.md 规律 1），"
                                    "该判别实验必须跨接 1pF 电容才成立"),
    "candidates": [
        "A) 克隆的 RESISTOR_VIRTUAL 没有真正进 SPICE 元素表（连通性网表与 SPICE deck 不同步）"
        "—— 若成立，P0 的「R=1k → I=5mA」其实也未被证实（探针当时在源节点上）",
        "B) ProbeExt 只能读源正极所在网络，读被电阻隔开的中间节点恒返回 0",
    ],
    "next_experiment": ("给分压器跨接 1pF 电容后重测中点：2.5V → 排除 A（电阻能导通、"
                        "中间节点可读），问题落到 C1；0V → 确认 A"),
}
json.dump(d, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("updated", P)
print("pass =", d["pass"])
