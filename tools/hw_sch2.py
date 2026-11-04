# -*- coding: utf-8 -*-
"""实验任务二 · 展示用电路图（显式布线，不带探针）。

和 hw_lab2.py 是同一张电路、同一组参数，只是坐标压缩过 ——
Multisim 打开时的默认缩放不随文件走，图纸太大就会被窗口裁掉，
而 Ctrl+滚轮在真机上会丢消息、方向也不稳定（见 hw_sch1.py 的注释）。
所以这里把整张图排进 ~830×420 的框里，默认视图一屏能装下。

布线原则和 hw_sch1.py 一致：电源轨在上、地母线在下、信号从左到右，
每个网络都手工给折点，不让自动 L 形路由穿过元件符号。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile          # noqa: E402
import hw_lab1             # noqa: E402
import hw_lab2             # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1")

POS = {
    "V1":   [100.0, 300.0],    # AC_VOLTAGE   1=(0,-27) 2=(0,27)
    "V2":   [40.0, 60.0],      # DC +12       1=(0,-18) 2=(0,18)
    "V3":   [200.0, 350.0],    # DC -12
    "R":    [220.0, 190.0],    # RESISTOR     1=(0,-22.5) 2=(0,22.5)
    "U1":   [400.0, 210.0],    # 741  IN-(356.29,243.43) IN+(356.29,207.43)
    #                            OUT(464.29,225.43) VS+(392.29,171.43) VS-(392.29,279.43)
    "R3":   [580.0, 207.5],    # 1=(580,185) 2=(580,230)
    "D1":   [680.0, 300.0],    # ZENER  K 在上
    "D2":   [680.0, 376.0],    # 同上 + rotate=180 → A 在上
    "RL":   [760.0, 300.0],
    "R1":   [830.0, 300.0],
    "R2":   [830.0, 380.0],
    "GND1": [860.0, 450.0],
}

Y_VCC = 30.0       # +12 轨
Y_GND = 450.0      # 地母线
X_FB = 870.0       # 反馈绕行用的右侧竖线


def build():
    hw_lab1.allow_parts()
    hw_lab2.allow_zener()
    ir = irmod.CircuitIR(name="sch2")

    def add(ref, fam, part, val=None, params=None, rot=0, vtext=None):
        ir.components.append(irmod.Component(
            refdes=ref, family=fam, part=part, value=val,
            params=params or {}, position=POS[ref], rotate=rot,
            value_text=vtext))

    add("V1", "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", None,
        {1: 5.0, 3: 0.0, 5: 1000.0, 7: 0.0})
    add("V2", "POWER_SOURCES", "DC_POWER", 12.0)
    add("V3", "POWER_SOURCES", "DC_POWER", -12.0)
    add("R", "RESISTOR", "RESISTOR_VIRTUAL", 2500.0)
    add("R1", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("R2", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("R3", "RESISTOR", "RESISTOR_VIRTUAL", 300.0)
    add("RL", "RESISTOR", "RESISTOR_VIRTUAL", 5000.0)
    add("U1", "OPAMP", "741")
    add("D1", "ZENER", "02DZ4.7", vtext="02DZ4.7")
    add("D2", "ZENER", "02DZ4.7", rot=180, vtext="02DZ4.7")
    add("GND1", "POWER_SOURCES", "GROUND")

    def net(name, pins, route="hv", star=None, routes=None):
        ir.nets.append(irmod.Net(name=name, pins=pins, route=route,
                                 star=star, routes=routes))

    net("vin", ["V1.1", "R.1"], star="V1.1",
        routes={"R.1": [[160.0, 167.5], [100.0, 167.5]]})
    net("n6", ["R.2", "U1.IN-"], route="vh")
    net("out", ["U1.OUT", "R3.1"], route="vh")
    net("vout", ["R3.2", "D1.K", "RL.1", "R1.1"], star="R3.2",
        routes={"D1.K": [[680.0, 230.0]],
                "RL.1": [[760.0, 230.0]],
                "R1.1": [[830.0, 230.0]]})
    net("mid", ["D1.A", "D2.A"])
    net("n2", ["U1.IN+", "R1.2", "R2.1"], star="R1.2",
        routes={"U1.IN+": [[330.0, 207.43], [330.0, 175.0],
                           [X_FB, 175.0], [X_FB, 340.0], [830.0, 340.0]]})
    net("vcc", ["U1.VS+", "V2.1"], star="U1.VS+",
        routes={"V2.1": [[40.0, Y_VCC], [392.29, Y_VCC]]})
    net("vee", ["U1.VS-", "V3.1"], star="U1.VS-",
        routes={"V3.1": [[200.0, 279.43]]})
    net("0", ["GND1.1", "V2.2", "V3.2", "V1.2", "D2.K", "RL.2", "R2.2"],
        star="GND1.1",
        routes={"V2.2": [[40.0, Y_GND]],
                "V3.2": [[200.0, Y_GND]],
                "V1.2": [[100.0, Y_GND]],
                "D2.K": [[680.0, Y_GND]],
                "RL.2": [[760.0, Y_GND]],
                "R2.2": [[830.0, Y_GND]]})

    ir.simulation.analysis = "transient"
    ir.simulation.start = 0.0
    ir.simulation.stop = 0.02
    ir.simulation.step = 5e-6
    ir.simulation.sample_rate = 200000.0
    return ir


def polish(ms14):
    """收尾：把稳压管符号里自带的引脚名小字（A/C）藏起来。

    元件库里这只稳压管的符号把引脚名画在符号旁边，缩到文档里就是几个
    看不清的蓝点，和作业原图也不一致。只改显示，不动电气。
    """
    import msmodel
    c = msmodel.Circuit.load(ms14)
    n = 0
    for ref in ("D1", "D2"):
        ciid = [i["ciid"] for i in c.components() if i["refdes"] == ref][0]
        item = c.symbol_of(ciid)
        if item is None:
            continue
        for el in item.iter():
            if el.tag.startswith("CIITPinSymText"):
                el.set("Hidden", "1")
                n += 1
    c.save(ms14)
    return n


def compile_display():
    ms14 = os.path.join(OUT, "sch2.ms14")
    rep = ir_compile.compile_ir(build(), ms14, verbose=False)
    n = polish(ms14)
    return ms14, rep, n


if __name__ == "__main__":
    ms14, rep, n = compile_display()
    print("编译 %d 字节 -> %s（隐藏引脚小字 %d 处）" % (rep["bytes"], ms14, n))
