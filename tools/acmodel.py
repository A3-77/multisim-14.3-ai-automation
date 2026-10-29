# -*- coding: utf-8 -*-
"""交流稳态的解析模型：复数阻抗 + 梯形网络求解（v0.10.0）。

为什么单独一个文件
------------------
这段数学原来写在 `ir_sim.theory()` 里，但 `ir_sim` 一 import 就拉 `msc`（COM），
于是**没有 Multisim 的机器连理论值都算不了，更别说单测**。理论值恰恰是
"独立复算"的基础 —— 它必须能在任何机器上跑，也必须在验收脚本之外被测试。

所以这里只放纯数学 + 纯 IR 遍历，不 import 任何 COM 相关模块。

它回答的问题只有一个
--------------------
**给定 IR 里的元件值和源频率，这个电路的理论增益和相位是多少？**

做法是从末级往回算每级看向负载的输入阻抗：

    Z[i] = 并联( 本级的到地元件 , 串联元件 + Z[i+1] )
    H_i  = Z[i+1] / ( 串联元件 + Z[i+1] )
    H    = Π H_i

好处是"同一节点两个到地元件"自动就是 R∥C，不需要为每种组合单写公式；
坏处是它只对**单主干 + 到地并联**成立 —— 所以入口先用 `layout.analyze()`
判拓扑，判不出来就返回 None，不硬算。

只认 R / C。出现二极管、电感、运放一律返回 None：没有线性模型就不给数值，
宁可没有，也不给一个"能算但错"的数。
"""
import math

import layout


def impedance(comp, f):
    """元件在频率 f（Hz）下的复阻抗。不认识的元件返回 None。"""
    w = 2.0 * math.pi * f
    if comp.family == "RESISTOR":
        v = float(comp.value or 0.0)
        return complex(v, 0.0) if v > 0 else None
    if comp.family == "CAPACITOR":
        c = float(comp.value or 0.0)
        return complex(0.0, -1.0 / (w * c)) if (c > 0 and w) else None
    return None


def parallel(zs):
    """复数并联。空列表 = 开路 → None；含 0 Ω = 短路 → 0。"""
    zs = [z for z in zs if z is not None]
    if not zs:
        return None
    y = 0j
    for z in zs:
        if z == 0:
            return complex(0.0, 0.0)
        y += 1.0 / z
    return 1.0 / y


def ladder_theory(ir):
    """单主干 + 到地并联的精确交流解。算不出来返回 None。

    返回字段：
        kind        固定 "ac_ladder"
        gain        |H|（输入 = 源正极所在网络，输出 = 末级网络）
        phase_deg   arg(H)
        freq        求解频率
        topology    layout 判出来的拓扑名（bypass / ladder / parallel_shunt …）
        z_in        从源正极看进去的输入阻抗模值
        stages      逐级的增益与相位（便于定位是哪一级对不上）
    """
    try:
        topo = layout.analyze(ir)
    except Exception:
        return None

    src = next((c for c in ir.components
                if c.family == "SIGNAL_VOLTAGE_SOURCES"), None)
    if src is None:
        return None
    f = float((src.params or {}).get(5) or 0.0)
    if not f:
        return None

    stages = topo.stages

    # 1) 每级的到地阻抗
    zsh = []
    for st in stages:
        zs = []
        for ref in st.shunts:
            comp = ir.component(ref)
            z = impedance(comp, f) if comp is not None else None
            if z is None:
                return None
            zs.append(z)
        zsh.append(parallel(zs))

    # 2) 串联元件阻抗
    zser = []
    for st in stages[:-1]:
        comp = ir.component(st.series)
        z = impedance(comp, f) if comp is not None else None
        if z is None:
            return None
        zser.append(z)

    # 3) 从末级往回
    z = zsh[-1]
    h = 1.0 + 0j
    per_stage = []
    for i in range(len(stages) - 2, -1, -1):
        denom = zser[i] + z if z is not None else zser[i]
        if denom == 0:
            return None
        h_i = (z / denom) if z is not None else 0j
        h *= h_i
        per_stage.append({
            "from": stages[i].net, "to": stages[i + 1].net,
            "series": stages[i].series,
            "gain": abs(h_i),
            "phase_deg": math.degrees(math.atan2(h_i.imag, h_i.real)),
        })
        z = parallel([zsh[i], denom])
        if z is None:
            return None

    per_stage.reverse()
    return {"kind": "ac_ladder", "gain": abs(h),
            "phase_deg": math.degrees(math.atan2(h.imag, h.real)),
            "freq": f, "topology": topo.kind,
            "n_series": topo.n_series, "n_shunt": topo.n_shunt,
            "z_in": abs(z) if z is not None else None,
            "stages": per_stage}
