# -*- coding: utf-8 -*-
"""P13：把 A/B/C 三步的证据写成 out/p13_diag.json 与 out/p13_fixed.json。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

diag = {
    "generated": "2026-10-24T20:50:00",
    "question": "中点恒 0V 是「克隆电阻不导通」还是「探针绑错网络」？",
    "verdict": "克隆的 RESISTOR_VIRTUAL 不导通（开路）；探针无罪。",
    "experiments": [
        {"step": "A1", "file": "out/p13_a1.ms14",
         "circuit": "V1(5V)-R1(1k)-R2(1k)-GND + C1(1pF) 中点跨接",
         "probe": "源网顶点 (500,300)",
         "outputs": ["V(探针1)"], "v": {"n": 2000, "first": 5.0, "last": 5.0,
                                        "min": 5.0, "max": 5.0},
         "conclusion": "源、探针、文件、地全部正常（对照组）"},
        {"step": "A2", "file": "out/p13_a2.ms14",
         "circuit": "同 A1",
         "probe": "中点网顶点 (650,385)",
         "outputs": ["V(探针1)"], "v": {"n": 2000, "first": 0.0, "last": 0.0,
                                        "min": 0.0, "max": 0.0},
         "conclusion": "期望 2.5V，实得 0V；与指挥方的 p13_divider（V(Probe1)，100 点全 0）一致"},
        {"step": "A3", "file": "out/p13_a3.ms14",
         "circuit": "V1(5V)-R1(1k)-中点-C1(1pF)-GND（去掉 R2）",
         "probe": "中点网顶点 (650,385)",
         "outputs": ["V(探针1)"], "v": {"n": 2000, "first": 0.0, "last": 0.0,
                                        "min": 0.0, "max": 0.0},
         "conclusion": "关键一步：无 R2 分流、中点只经 R1 接 5V、1pF 直流开路 → 应为 5V，实得 0V "
                       "=> R1 不导通"},
        {"step": "A4", "file": "out/p13_a4.ms14",
         "circuit": "V1(5V)-导线-C1(1pF)-GND（不放任何电阻，中点直接接源）",
         "probe": "导线拐点 (650,300)",
         "outputs": ["V(探针1)"], "v": {"n": 2000, "first": 5.0, "last": 5.0,
                                        "min": 5.0, "max": 5.0},
         "conclusion": "排除探针嫌疑：探针能读任何带拐点的网络，只要该网络真的接在源上"},
    ],
    "netlist_evidence": {
        "p13_a3_ReportNetlist": ["0: GND, GND, C1.2, V1.2", "1: R1.1, V1.1", "2: R1.2, C1.1"],
        "note": "Multisim 自己的连通性表是对的（R1 两条腿分别落在 1/2），"
                "但 SPICE 侧没有把这个电阻算进去 —— 网表表 ≠ SPICE deck",
    },
    "static_evidence": {
        "clone_vs_donor_R1": "donor_spice 原 R1(50Ω) 与克隆 R1(1kΩ) 逐槽比对：47 槽中仅槽 2(取值)、"
                             "槽 41/42(显示串) 不同，其余完全一致",
        "ports_order": "CiComponent/Ports 顺序 [pin1, pin2]，与 donor 一致",
        "portid": "CIITPinSymbolComp@PortID 分别指向本元件的两个新 CiPort（绑定 2/2）",
        "node_membership": "CiPort/Nodes 反向引用齐全，CiNode/Ports 成员正确",
        "attributes3": "Attributes[3] 在 donor 与克隆里都是空 <Item />，未损坏",
        "spice_template": "Attributes[1] 模板一致：r%p %t1 %t2 #1 vres%p %v4?TEMP=#5... .model vres%p r(...)",
        "params": "doubles 12 个，值 ['0.','1000.','0.','0.','1.','27.','1.','0.','1.','0.','1.','27.']",
    },
    "ruled_out": ["探针位置/绑定（A4 反证）", "源与地（A1 反证）",
                  "PortID 重映射（P11 已修，本次复核绑定 2/2）",
                  "端子顺序与节点成员（静态全对）",
                  "取值未写入（RLCValue=1000）"],
    "still_open": "SPICE 元素行为：电阻在 Multisim 连通性网表里存在，但仿真侧等效开路。"
                  "Multisim 的 LogFile 只记插件加载（无 SPICE deck），COM 的 ReportNetlist 只给连通性表，"
                  "所以还缺一份真正的 SPICE 网表来定位（见 next_steps）。",
    "next_steps": [
        "拿 SPICE deck：Multisim GUI → Simulate → Analyses → 任意分析 → Netlist 页，或 Export to SPICE，"
        "对 p13_a3.ms14 导出 .cir 看 R1 的元素行",
        "把 R1 换成库里**非虚拟**电阻（DB 里 RESISTOR 家族的实体型号，如 R_1k），"
        "验证是否只有 *_VIRTUAL 类元件有这个毛病",
        "用 7812.ms12 里的原装电阻做同构分压器（不克隆，直接在其文件内改），确认基线",
    ],
}

json.dump(diag, open(os.path.join(ROOT, "out", "p13_diag.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("written out/p13_diag.json")

fixed = {
    "generated": "2026-10-24T20:50:00",
    "status": "blocked",
    "blocked_by": "B：电阻不导通的原因未定位到可修的字段（静态全对，缺 SPICE deck）",
    "acceptance_regenerated": False,
    "reason_not_regenerated": "C 依赖 B。在电阻仍开路的情况下重新生成 acceptance.ms14 只会把"
                              "P0 的验收文件覆盖成另一个 0V 版本，故保持原文件不动，等根因修好再重建。",
    "p0_verdict": {
        "claim": "V=5V、R=1k → I=5mA",
        "status": "不成立（未证实）",
        "why": "P0 的探针落在 net1 = V1.1 + R1.1，即源正极节点，读到的 5V 是源电压；"
               "电流从未被测量，且本次 A1/A2/A3/A4 证明该电阻在仿真里是开路的。",
        "what_is_still_true": "从空白 .ms14 生成电路、Multisim 能打开、探针能注册并读数、"
                              "元件参数可读写 —— 这些依然成立；不成立的是「电阻在导通」这个物理结论。",
    },
    "fix_candidates": [
        "若 SPICE deck 里 R1 的元素行缺失/语法错：修 CiaSpiceTmpltExprt 展开（%p / %t1 / %t2 的取值来源）",
        "若只有 *_VIRTUAL 类出问题：改用实体型号电阻作为模板，或在 add() 里补 CiModel",
    ],
}
json.dump(fixed, open(os.path.join(ROOT, "out", "p13_fixed.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("written out/p13_fixed.json")
