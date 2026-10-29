# -*- coding: utf-8 -*-
"""layout.py 的纯逻辑测试（不需要 Multisim，任意位数 Python）。

这一层测的是"拓扑判断"，不是"坐标好不好看"。覆盖：

    支持类
      shunt_load     单元件跨在电源上（直流 5V + 电阻）
      bypass         一阶 RC 低通
      divider        电阻分压
      tee            T 型网络
      ladder         二阶 RC 梯形（第二次 Agent 验收的真实拓扑）
      series_chain   空载串联
      parallel_shunt 同一节点 2 个到地元件（v0.10.0）：
                     分压 + 旁路电容 / RC 并联负载 / 两个电阻并联

    拒绝类（必须给出可执行的 hint，不能只说"失败"）
      fork           一个节点两条向下的主干
      parallel_shunt 一个节点 3 个到地元件（超过 v0.10.0 的上限 2）
      island         和电源不连通的元件
      open_pin       元件另一端没接线
      too_many_stages 级数超限
      多电源 / 无地 / 源负极没接地

    （`cycle` 有防御性检查，但正常路径下 fork 会先拦下来，所以测不到。）

    坐标性质
      所有元件都有坐标且互不重叠
      串联元件按级向右、并联元件挂在本级下方
      同一节点的 2 个并联元件在同一行、以本级列为对称轴
      同一份 IR 两次调用结果完全一致（纯函数，无随机）

跑法：
    python tools/test_layout.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import circuit_ir as irmod   # noqa: E402
import layout as L           # noqa: E402

npass = 0
nfail = 0

AC = ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE")
DC = ("POWER_SOURCES", "DC_POWER")
R = ("RESISTOR", "RESISTOR_VIRTUAL")
C = ("CAPACITOR", "CAPACITOR_VIRTUAL")
G = ("POWER_SOURCES", "GROUND")


def check(name, cond, detail=""):
    global npass, nfail
    if cond:
        npass += 1
        print("  %-50s OK   %s" % (name, detail))
    else:
        nfail += 1
        print("  %-50s FAIL %s" % (name, detail))


def build(name, comps, nets):
    """comps: [(refdes, (family, part), value)]，nets: [(name, [pins])]。"""
    ir = irmod.CircuitIR(name=name)
    for ref, key, val in comps:
        ir.components.append(irmod.Component(refdes=ref, family=key[0],
                                             part=key[1], value=val))
    for nm, pins in nets:
        ir.nets.append(irmod.Net(name=nm, pins=list(pins)))
    return ir


def expect_err(name, fn, code, reason=None, hint_sub=None):
    try:
        fn()
    except L.LayoutError as e:
        ok = (e.code == code)
        if ok and reason:
            ok = e.context.get("reason") == reason
        if ok and hint_sub:
            blob = "%s %s" % (e.hint or "", e.message or "")
            ok = hint_sub in blob
        check(name, ok, "%s/%s" % (e.code, e.context.get("reason")))
        return e
    except Exception as e:
        check(name, False, "抛了别的异常：%r" % (e,))
        return None
    check(name, False, "没有报错")
    return None


# ---------------------------------------------------------------------------
# 各模板的最小电路
# ---------------------------------------------------------------------------
def ir_dc_shunt():
    """直流 5V + 1kΩ 到地（v0.5.0 验收电路）。"""
    return build("dc_shunt",
                 [("V1", DC, 5.0), ("R1", R, 1000.0), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("0", ["R1.2", "V1.2", "GND1.1"])])


def ir_rc1():
    """一阶 RC 低通：V1 - R1 - n1 - C1 - 0。"""
    return build("rc1",
                 [("V1", AC, 1.0), ("R1", R, 10000.0), ("C1", C, 33e-9),
                  ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "C1.1"]),
                  ("0", ["C1.2", "V1.2", "GND1.1"])])


def ir_divider():
    """电阻分压：V1 - R1 - n1 - R2 - 0，输出取 n1。"""
    return build("divider",
                 [("V1", DC, 10.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                  ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "R2.1"]),
                  ("0", ["R2.2", "V1.2", "GND1.1"])])


def ir_tee():
    """T 型：R1 串进来，n1 上分两路 —— R2 继续向前，R3 下地。

    n2 只有 R2.2 一个引脚（空载输出）。这是 T 型网络的原始形状；
    真正仿真前要接负载，那是 validate() 的事，不是布局的事。
    """
    return build("tee",
                 [("V1", DC, 10.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                  ("R3", R, 1000.0), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "R2.1", "R3.1"]),
                  ("n2", ["R2.2"]),
                  ("0", ["R3.2", "V1.2", "GND1.1"])])


def ir_ladder2():
    """二阶 RC 梯形 —— 第二次 Agent 验收实际建出来的拓扑。

    in  [V1.1, R1.1]
    n1  [R1.2, C1.1, R2.1]      三引脚节点，v0.6.x 在这里报 LAYOUT_UNSUPPORTED
    n2  [R2.2, C2.1]
    0   [C1.2, C2.2, V1.2, GND1.1]
    """
    return build("rc2",
                 [("V1", AC, 1.0), ("R1", R, 10000.0), ("R2", R, 10000.0),
                  ("C1", C, 8.2e-9), ("C2", C, 8.2e-9), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "C1.1", "R2.1"]),
                  ("n2", ["R2.2", "C2.1"]),
                  ("0", ["C1.2", "C2.2", "V1.2", "GND1.1"])])


def ir_divider_bypass():
    """分压器 + 旁路电容（v0.10.0）：V1 - R1 - n1，n1 上 R2 与 C1 一起下地。

    这是教学电路里最常见的一张图：分压给静态工作点，电容旁路交流。
    """
    return build("divider_bypass",
                 [("V1", DC, 10.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                  ("C1", C, 100e-9), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "R2.1", "C1.1"]),
                  ("0", ["R2.2", "C1.2", "V1.2", "GND1.1"])])


def ir_rc_parallel():
    """RC 并联负载（v0.10.0 真机验收电路）：V1 - R1 - n1，n1 上 C1 || R2 下地。

    R1=R2=1kΩ，C1=159.155nF @ 1kHz → Z_C = 1kΩ，Z_par = 500-j500，
    增益 0.4472 ∠ -26.565°。三个数字都是能手算的整数关系，便于独立复算。
    """
    return build("rc_parallel",
                 [("V1", AC, 1.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                  ("C1", C, 159.155e-9), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1"]),
                  ("n1", ["R1.2", "C1.1", "R2.1"]),
                  ("0", ["C1.2", "R2.2", "V1.2", "GND1.1"])])


def main():
    print("=" * 78)
    print("layout 纯逻辑测试：拓扑判断 + 坐标")
    print("=" * 78)

    # ---------------------------------------------------------------- 1
    print("\n[1] 支持类：6 种模板都能被正确识别")
    t = L.analyze(ir_dc_shunt())
    check("直流 5V+电阻 -> shunt_load", t.kind == "shunt_load", t.kind)
    check("  0 级主干 / 1 个到地", (t.n_series, t.n_shunt) == (0, 1),
          "%d/%d" % (t.n_series, t.n_shunt))
    check("  输出网 = in", t.out_net == "in", t.out_net)

    t = L.analyze(ir_rc1())
    check("一阶 RC -> bypass", t.kind == "bypass", t.kind)
    check("  1 级主干 / 1 个到地", (t.n_series, t.n_shunt) == (1, 1),
          "%d/%d" % (t.n_series, t.n_shunt))
    check("  输出网 = n1", t.out_net == "n1", t.out_net)
    check("  主干 R1 / 到地 C1",
          (t.stages[0].series, t.stages[1].shunt) == ("R1", "C1"),
          "%s / %s" % (t.stages[0].series, t.stages[1].shunt))

    t = L.analyze(ir_divider())
    check("电阻分压 -> divider", t.kind == "divider", t.kind)
    check("  输出网 = n1（中间节点）", t.out_net == "n1", t.out_net)

    t = L.analyze(ir_tee())
    check("T 型 -> tee", t.kind == "tee", t.kind)
    check("  2 级主干 / 1 个到地", (t.n_series, t.n_shunt) == (2, 1),
          "%d/%d" % (t.n_series, t.n_shunt))
    check("  并联在中间级（index=1）",
          t.stages[1].shunt == "R3", t.stages[1].shunt)
    check("  输出网 = n2", t.out_net == "n2", t.out_net)

    t = L.analyze(ir_ladder2())
    check("二阶 RC -> ladder", t.kind == "ladder", t.kind)
    check("  2 级主干 / 2 个到地", (t.n_series, t.n_shunt) == (2, 2),
          "%d/%d" % (t.n_series, t.n_shunt))
    check("  三引脚节点 n1 被识别为正常级",
          [s.net for s in t.stages] == ["in", "n1", "n2"],
          str([s.net for s in t.stages]))
    check("  C1 在 n1、C2 在 n2",
          (t.stages[1].shunt, t.stages[2].shunt) == ("C1", "C2"),
          "%s / %s" % (t.stages[1].shunt, t.stages[2].shunt))
    check("  输出网 = n2", t.out_net == "n2", t.out_net)

    # 空载串联：末端 n2 是个开路节点（只有 R2.2 一个引脚）。
    # 这种电路 validate() 会拦，但拓扑层应该照实识别成"两级串联、没有到地支路"。
    chain = build("series",
                  [("V1", DC, 5.0), ("R1", R, 100.0), ("R2", R, 100.0),
                   ("GND1", G, None)],
                  [("in", ["V1.1", "R1.1"]),
                   ("n1", ["R1.2", "R2.1"]),
                   ("n2", ["R2.2"]),
                   ("0", ["V1.2", "GND1.1"])])
    t = L.analyze(chain)
    check("空载串联 -> series_chain", t.kind == "series_chain", t.kind)
    check("  2 级主干 / 0 个到地", (t.n_series, t.n_shunt) == (2, 0),
          "%d/%d" % (t.n_series, t.n_shunt))

    # ---- v0.10.0：同一节点 2 个到地元件 ----
    t = L.analyze(ir_divider_bypass())
    check("分压 + 旁路电容 -> parallel_shunt", t.kind == "parallel_shunt", t.kind)
    check("  1 级主干 / 2 个到地（数元件，不是数级）",
          (t.n_series, t.n_shunt) == (1, 2),
          "%d/%d" % (t.n_series, t.n_shunt))
    check("  两个到地元件都记在同一级",
          t.stages[1].shunts == ["R2", "C1"], str(t.stages[1].shunts))
    check("  shunt 别名仍然只返回第一个", t.stages[1].shunt == "R2",
          str(t.stages[1].shunt))
    check("  输出网 = n1", t.out_net == "n1", t.out_net)

    t = L.analyze(ir_rc_parallel())
    check("RC 并联负载 -> parallel_shunt", t.kind == "parallel_shunt", t.kind)
    check("  1 级主干 / 2 个到地", (t.n_series, t.n_shunt) == (1, 2),
          "%d/%d" % (t.n_series, t.n_shunt))
    check("  elements 按信号流向列出全部 4 个元件",
          t.elements == ["R1", "C1", "R2"], str(t.elements))

    # 0 级主干 + 2 个并联到地：两个电阻跨在电源上（等效一个电阻）
    par = build("parallel",
                [("V1", DC, 5.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                 ("GND1", G, None)],
                [("in", ["V1.1", "R1.1", "R2.1"]),
                 ("0", ["R1.2", "R2.2", "V1.2", "GND1.1"])])
    t = L.analyze(par)
    check("两个电阻跨在电源上 -> parallel_shunt（不再是拒绝）",
          t.kind == "parallel_shunt", t.kind)
    check("  0 级主干 / 2 个到地", (t.n_series, t.n_shunt) == (0, 2),
          "%d/%d" % (t.n_series, t.n_shunt))

    # ---------------------------------------------------------------- 2
    print("\n[2] 拒绝类：不支持的拓扑必须说清原因 + 下一步")
    fork = build("fork",
                 [("V1", AC, 1.0), ("R1", R, 1000.0), ("R3", R, 1000.0),
                  ("C1", C, 1e-6), ("C2", C, 1e-6), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1", "R3.1"]),
                  ("n1", ["R1.2", "C1.1"]),
                  ("n2", ["R3.2", "C2.1"]),
                  ("0", ["C1.2", "C2.2", "V1.2", "GND1.1"])])
    expect_err("一个节点两条主干 -> fork", lambda: L.analyze(fork),
               "LAYOUT_UNSUPPORTED", "fork", "单主干")

    # v0.10.0 放开到 2 个，3 个仍然拒绝
    par3 = build("parallel3",
                 [("V1", DC, 5.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                  ("R3", R, 1000.0), ("GND1", G, None)],
                 [("in", ["V1.1", "R1.1", "R2.1", "R3.1"]),
                  ("0", ["R1.2", "R2.2", "R3.2", "V1.2", "GND1.1"])])
    expect_err("一个节点 3 个到地元件 -> parallel_shunt", lambda: L.analyze(par3),
               "LAYOUT_UNSUPPORTED", "parallel_shunt", "上限")

    island = build("island",
                   [("V1", DC, 5.0), ("R1", R, 1000.0), ("R8", R, 1.0),
                    ("R9", R, 1.0), ("GND1", G, None)],
                   [("in", ["V1.1", "R1.1"]),
                    ("0", ["R1.2", "V1.2", "GND1.1"]),
                    ("x", ["R8.1", "R9.1"]),
                    ("y", ["R8.2", "R9.2"])])
    expect_err("悬空子电路 -> island", lambda: L.analyze(island),
               "LAYOUT_UNSUPPORTED", "island", "不连通")

    openp = build("open_pin",
                  [("V1", DC, 5.0), ("R1", R, 1000.0), ("GND1", G, None)],
                  [("in", ["V1.1", "R1.1"]),
                   ("0", ["V1.2", "GND1.1"])])
    expect_err("另一端没接 -> open_pin", lambda: L.analyze(openp),
               "LAYOUT_UNSUPPORTED", "open_pin", "接线")

    # 5 级串联 + 末端电容：超过 MAX_STAGES（4 级）
    longc = [("V1", AC, 1.0), ("GND1", G, None), ("C1", C, 1e-6)] + \
            [("R%d" % i, R, 1000.0) for i in range(1, 6)]
    longn = [("in", ["V1.1", "R1.1"]),
             ("n1", ["R1.2", "R2.1"]),
             ("n2", ["R2.2", "R3.1"]),
             ("n3", ["R3.2", "R4.1"]),
             ("n4", ["R4.2", "R5.1"]),
             ("n5", ["R5.2", "C1.1"]),
             ("0", ["C1.2", "V1.2", "GND1.1"])]
    expect_err("5 级主干 -> too_many_stages",
               lambda: L.analyze(build("long", longc, longn)),
               "LAYOUT_UNSUPPORTED", "too_many_stages", "上限")

    two_src = build("two_src",
                    [("V1", DC, 5.0), ("V2", DC, 5.0), ("R1", R, 1000.0),
                     ("GND1", G, None)],
                    [("in", ["V1.1", "R1.1", "V2.1"]),
                     ("0", ["R1.2", "V1.2", "V2.2", "GND1.1"])])
    expect_err("两个电源 -> MULTIPLE_SOURCES", lambda: L.analyze(two_src),
               "MULTIPLE_SOURCES", None, "单电源")

    nognd = build("nognd",
                  [("V1", DC, 5.0), ("R1", R, 1000.0)],
                  [("in", ["V1.1", "R1.1"]),
                   ("0", ["R1.2", "V1.2"])])
    expect_err("没有地 -> NO_GROUND", lambda: L.analyze(nognd), "NO_GROUND")

    # 回路是通的，但电源负极落在 z 网、GROUND 单独挂在 0 网 —— 单电源前提不成立
    negfloat = build("negfloat",
                     [("V1", DC, 5.0), ("R1", R, 1000.0), ("R2", R, 1000.0),
                      ("GND1", G, None)],
                     [("in", ["V1.1", "R1.1"]),
                      ("y", ["R1.2", "R2.1"]),
                      ("z", ["V1.2", "R2.2"]),
                      ("0", ["GND1.1"])])
    expect_err("源负极没接地 -> SOURCE_NOT_GROUNDED",
               lambda: L.analyze(negfloat),
               "SOURCE_NOT_GROUNDED", None, "负极")

    # ---------------------------------------------------------------- 3
    print("\n[3] 坐标：所有元件都有位置、互不重叠、能看出层级")
    for name, ir in (("dc_shunt", ir_dc_shunt()), ("rc1", ir_rc1()),
                     ("divider", ir_divider()), ("tee", ir_tee()),
                     ("ladder2", ir_ladder2()),
                     ("divider_bypass", ir_divider_bypass()),
                     ("rc_parallel", ir_rc_parallel())):
        topo, pos = L.plan_ir(ir)
        refs = [c.refdes for c in ir.components]
        check("%s：每个元件都有坐标" % name,
              all(r in pos for r in refs),
              "缺 %s" % [r for r in refs if r not in pos])
        pts = [tuple(pos[r]) for r in refs]
        check("%s：坐标互不重叠" % name, len(set(pts)) == len(pts),
              "%d 个元件 / %d 个不同坐标" % (len(pts), len(set(pts))))
        check("%s：坐标是纯数字" % name,
              all(isinstance(v, (int, float)) for p in pts for v in p))

    topo, pos = L.plan_ir(ir_ladder2())
    check("ladder2：串联元件按级向右递增",
          pos["R1"][0] < pos["R2"][0],
          "R1.x=%g R2.x=%g" % (pos["R1"][0], pos["R2"][0]))
    check("ladder2：并联元件挂在主干下方",
          pos["C1"][1] > pos["R1"][1] and pos["C2"][1] > pos["R2"][1],
          "C1.y=%g R1.y=%g" % (pos["C1"][1], pos["R1"][1]))
    check("ladder2：C1 与 R1 同一列附近（本级节点）",
          abs(pos["C1"][0] - (pos["R1"][0] + L.DX / 2.0)) < 1e-9,
          "C1.x=%g R1.x=%g" % (pos["C1"][0], pos["R1"][0]))
    check("ladder2：地在最下方",
          pos["GND1"][1] > max(pos[c.refdes][1] for c in ir_ladder2().components
                               if c.part != "GROUND"),
          "GND.y=%g" % pos["GND1"][1])

    check("纯函数：两次调用结果完全一致",
          L.plan_ir(ir_ladder2())[1] == L.plan_ir(ir_ladder2())[1])

    # ---- v0.10.0：并联到地的几何 ----
    topo, pos = L.plan_ir(ir_rc_parallel())
    cx = L._col_x(1)                      # 第 1 级的列（n1 所在列）
    check("rc_parallel：两个并联元件在同一行",
          pos["C1"][1] == pos["R2"][1] == L.Y_SHUNT,
          "C1.y=%g R2.y=%g" % (pos["C1"][1], pos["R2"][1]))
    check("rc_parallel：两个并联元件左右分开（x 不同）",
          abs(pos["C1"][0] - pos["R2"][0]) == L.SHUNT_DX,
          "C1.x=%g R2.x=%g 差=%g"
          % (pos["C1"][0], pos["R2"][0], abs(pos["C1"][0] - pos["R2"][0])))
    check("rc_parallel：以本级列为对称轴",
          abs((pos["C1"][0] + pos["R2"][0]) / 2.0 - cx) < 1e-9,
          "中点=%g 本级列=%g" % ((pos["C1"][0] + pos["R2"][0]) / 2.0, cx))
    check("rc_parallel：并联元件仍在串联元件下方",
          pos["C1"][1] > pos["R1"][1] and pos["R2"][1] > pos["R1"][1])
    check("rc_parallel：两并联元件不与串联元件同 x（不叠符号）",
          all(abs(p[0] - pos["R1"][0]) > 20 for p in (pos["C1"], pos["R2"])),
          "R1.x=%g C1.x=%g R2.x=%g" % (pos["R1"][0], pos["C1"][0],
                                       pos["R2"][0]))

    # 单个到地元件的坐标必须和 v0.9 完全一致（不能因为新逻辑漂移）
    topo, pos = L.plan_ir(ir_rc1())
    check("回归：单并联元件仍在本级列正中（x 偏移 0）",
          abs(pos["C1"][0] - L._col_x(1)) < 1e-9, "C1.x=%g" % pos["C1"][0])
    check("回归：单并联元件的 y 仍是 Y_SHUNT",
          pos["C1"][1] == L.Y_SHUNT, "C1.y=%g" % pos["C1"][1])

    # ---------------------------------------------------------------- 4
    print("\n[4] 拓扑摘要能被 Agent 读懂")
    t = L.analyze(ir_ladder2())
    d = t.to_dict()
    check("to_dict 有 kind/n_series/n_shunt/stages",
          set(d) == {"kind", "source", "ground", "in_net", "gnd_net",
                     "out_net", "n_series", "n_shunt", "stages"}, str(sorted(d)))
    check("stages 每项含 index/net/series/shunt/shunts",
          all(set(s) == {"index", "net", "series", "shunt", "shunts"}
              for s in d["stages"]),
          str(d["stages"][1]))
    check("shunts 是列表（老代码用 shunt 仍能工作）",
          isinstance(d["stages"][1]["shunts"], list)
          and d["stages"][1]["shunt"] == d["stages"][1]["shunts"][0],
          str(d["stages"][1]))
    check("summary() 能打印出级数",
          "ladder" in t.summary() and "n1" in t.summary())
    print("  --- summary 示例 ---")
    for line in t.summary().split("\n"):
        print("  " + line)

    print("\n" + "=" * 78)
    print("结果：%d 通过 / %d 失败" % (npass, nfail))
    print("=" * 78)
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
