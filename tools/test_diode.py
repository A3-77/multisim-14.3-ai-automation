# -*- coding: utf-8 -*-
"""DIODE / 1N4007G 的自动化测试（**不需要 Multisim**，纯逻辑 + 编译）。

覆盖什么
--------
    [1] registry 数据完整性      donor 里读出来的引脚 / 几何 / SPICE 模板 / 来源
    [2] IR 白名单合并            registry enabled 的才进 SUPPORTED，legacy 5 条不变
    [3] 会话层                   add_component 能加二极管、引脚只认 A/K、错误码清楚
    [4] 布局与准入               halfwave_rectifier 模板 + 四种拒绝姿势
    [5] 编译                     .ms14 真能写出来、donor 来源写进报告、探针落点避开引脚
    [6] 回归                     一阶 RC 的拓扑判定与坐标一个字节没变

**不覆盖**：真机仿真。那一段必须开 Multisim，见
`tools/agent_acceptance/run_diode.py`（Agent 视角的端到端验收）。

跑法：
    runtime\\py32\\python.exe tools/test_diode.py
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import circuit_ir as irmod      # noqa: E402
import circuit_session as S     # noqa: E402
import ir_compile               # noqa: E402
import layout as L              # noqa: E402
import registry as reg          # noqa: E402

npass = 0
nfail = 0

AC = ("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE")
R = ("RESISTOR", "RESISTOR_VIRTUAL")
C = ("CAPACITOR", "CAPACITOR_VIRTUAL")
G = ("POWER_SOURCES", "GROUND")
D = ("DIODE", "1N4007G")

WORK = os.path.join(ROOT, "out", "test_diode")


def check(name, cond, detail=""):
    global npass, nfail
    if cond:
        npass += 1
        print("  %-56s OK   %s" % (name, detail))
    else:
        nfail += 1
        print("  %-56s FAIL %s" % (name, detail))


def expect_err(name, fn, code, reason=None, hint_sub=None):
    try:
        fn()
    except Exception as e:
        got = getattr(e, "code", None) or type(e).__name__
        ok = (got == code)
        if ok and reason is not None:
            ok = (getattr(e, "context", {}) or {}).get("reason") == reason
        if ok and hint_sub:
            blob = "%s %s" % (getattr(e, "hint", "") or "", getattr(e, "message", "") or "")
            ok = hint_sub in blob
        check(name, ok, "" if ok else "code=%r reason=%r msg=%s"
              % (got, (getattr(e, "context", {}) or {}).get("reason"),
                 (getattr(e, "message", "") or "")[:70]))
        return e
    check(name, False, "没有抛错")
    return None


def build(name, comps, nets, probes=()):
    """comps: [(refdes, (family, part), value)]，nets: [(name, [pins])]。"""
    ir = irmod.CircuitIR(name=name)
    for ref, key, val in comps:
        ir.components.append(irmod.Component(refdes=ref, family=key[0],
                                             part=key[1], value=val))
    for nm, pins in nets:
        ir.nets.append(irmod.Net(name=nm, pins=list(pins)))
    for pname, net in probes:
        ir.probes.append(irmod.Probe(refdes=pname, net=net))
    return ir


def ir_halfwave():
    """V1(5V/50Hz) -> D1 -> R1(1k) -> GND，两个探针。

    引脚写真实名（V1.1 / V1.2）—— 和会话层落盘的形状一致（connect 存的是
    归一化后的真实引脚名）。'+' / '-' 是 IR 层的输入别名，只在手写 JSON 里出现。
    """
    ir = build("halfwave", [
        ("V1", AC, 5.0), ("D1", D, None), ("R1", R, 1000.0), ("GND1", G, None),
    ], [
        ("in", ["V1.1", "D1.A"]),
        ("out", ["D1.K", "R1.1"]),
        ("0", ["V1.2", "R1.2", "GND1.1"]),
    ], [("P_in", "in"), ("P_out", "out")])
    ir.simulation.analysis = "transient"
    ir.simulation.stop = 0.1
    ir.simulation.sample_rate = 100000.0
    return ir


def ir_rc():
    """一阶 RC 低通（v0.7/v0.8 验收用的那个）。"""
    ir = build("rc", [
        ("V1", AC, 1.0), ("R1", R, 1000.0), ("C1", C, 3.3e-7), ("GND1", G, None),
    ], [
        ("in", ["V1.1", "R1.1"]),
        ("out", ["R1.2", "C1.1"]),
        ("0", ["V1.2", "C1.2", "GND1.1"]),
    ], [("P_out", "out"), ("P_in", "in")])
    ir.simulation.analysis = "transient"
    ir.simulation.stop = 0.006
    ir.simulation.sample_rate = 200000.0
    return ir


# ---------------------------------------------------------------------------
def t1_registry():
    print("\n[1] registry 数据完整性（引脚/几何/模板/donor 都来自真实 .ms14）")
    e = reg.spec("DIODE", "1N4007G")
    check("registry 里有 DIODE/1N4007G", e is not None)
    if not e:
        return
    check("引脚顺序是 A, K", e["pins"] == ["A", "K"], str(e["pins"]))
    check("两个引脚都有几何坐标",
          set(e["pin_geometry"]) == {"A", "K"},
          str(e["pin_geometry"]))
    check("引脚几何是竖直的（A 在下、K 在上）",
          e["orientation"] == "vertical"
          and e["pin_geometry"]["A"][1] > e["pin_geometry"]["K"][1],
          "extent=%s" % (e["pin_extent"],))
    check("SPICE 模板按引脚名引用",
          e["spice_template"] == "d%p %tA %tK %m", e["spice_template"])
    check("参数槽 0 个（型号决定一切，不接受 value）",
          e["n_params"] == 0, str(e["n_params"]))
    check("donor 在仓库里（不依赖 Multisim 安装目录）",
          e["donor"]["in_repo"] is True, e["donor"]["file"])
    check("donor 文件真的存在", reg.donor_ready(e), reg.donor_path(e))
    check("refdes 前缀由 donor 位号推出来", e["refdes_prefix"] == "D",
          e["refdes_prefix"])
    check("registry 里只有 1 种 enabled",
          reg.enabled_keys() == ["DIODE/1N4007G"], str(reg.enabled_keys()))
    check("目录里远不止 1 种（存在 ≠ 已支持）",
          len(reg.all_keys()) > 100, "%d 种" % len(reg.all_keys()))


def t2_ir_whitelist():
    print("\n[2] IR 白名单：registry 合并，legacy 5 条原样不动")
    check("registry 加载没有报错", irmod.REGISTRY_LOAD_ERROR is None,
          str(irmod.REGISTRY_LOAD_ERROR))
    check("SUPPORTED 里有二极管", D in irmod.SUPPORTED)
    check("二极管 spec 只有 A/K、没有别名",
          irmod.SUPPORTED[D]["pins"] == ("A", "K")
          and irmod.SUPPORTED[D]["aliases"] == {},
          str(irmod.SUPPORTED[D]))

    legacy_expect = {
        AC: {"pins": ("1", "2"), "aliases": {"+": "1", "-": "2"}},
        ("POWER_SOURCES", "DC_POWER"): {"pins": ("1", "2"),
                                        "aliases": {"+": "1", "-": "2"}},
        R: {"pins": ("1", "2"), "aliases": {}},
        C: {"pins": ("1", "2"), "aliases": {}},
        G: {"pins": ("1",), "aliases": {}},
    }
    same = all(irmod.SUPPORTED[k]["pins"] == v["pins"]
               and irmod.SUPPORTED[k]["aliases"] == v["aliases"]
               for k, v in legacy_expect.items())
    check("5 种 legacy 的 pins/aliases 与 v0.8 完全一致", same)
    check("legacy 条目没有 origin 字段（没被 registry 覆盖）",
          all("origin" not in irmod.SUPPORTED[k] for k in legacy_expect))

    ir = ir_halfwave()
    errs = ir.validate()
    check("半波整流 IR 通过 validate", not errs, str(errs[:2]))

    ir_alias = ir_halfwave()
    ir_alias.nets[0].pins = ["V1.+", "D1.A"]      # 别名写法也应该通过
    check("源的 '+' 别名仍能归一化", not ir_alias.validate(),
          str(ir_alias.validate()[:1]))

    ir_bad = ir_halfwave()
    ir_bad.nets[0].pins = ["V1.1", "D1.1"]
    check("二极管没有引脚 '1'",
          any("没有引脚" in x for x in ir_bad.validate()),
          str(ir_bad.validate()[:1]))


def t3_session():
    print("\n[3] 会话层：能加、能连、错误码清楚")
    S.SESS_ROOT = os.path.join(WORK, "sessions")
    shutil.rmtree(S.SESS_ROOT, ignore_errors=True)
    c = S.create_circuit("t_diode")
    cid = c["circuit_id"]

    r = S.add_component(cid, "DIODE", "1N4007G", refdes="D1")
    comp = r["component"]
    check("add_component 接受 DIODE/1N4007G", comp["family"] == "DIODE")
    check("自动/显式位号都是 D 前缀", comp["refdes"] == "D1", comp["refdes"])
    check("返回的 pins 是 A/K", comp["pins"] == ["A", "K"], str(comp["pins"]))
    check("value 是 None（不需要也不接受）", comp["value"] is None)
    check("topology.complete=False（还没接完）",
          r["topology"]["complete"] is False)

    expect_err("给二极管传 value 会被拒绝",
               lambda: S.add_component(cid, "DIODE", "1N4007G", refdes="D2",
                                       value=0.7),
               "BAD_ARGUMENT")
    expect_err("不存在的型号仍然报 UNKNOWN_COMPONENT_TYPE",
               lambda: S.add_component(cid, "DIODE", "1N9999", refdes="D3"),
               "UNKNOWN_COMPONENT_TYPE")
    err = expect_err("BJT 还没 enable（存在 ≠ 已支持）",
                     lambda: S.add_component(cid, "BJT_NPN", "2N2222A", refdes="Q1"),
                     "UNKNOWN_COMPONENT_TYPE")
    if err:
        check("hint 里说清了『扫到过 ≠ 已支持』",
              "扫到过" in (err.hint or "") or "已支持" in (err.hint or ""),
              (err.hint or "")[:60])

    S.add_component(cid, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", refdes="V1",
                    value=5.0, parameters={"frequency": 50})
    S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL", refdes="R1", value=1000)
    S.add_component(cid, "POWER_SOURCES", "GROUND", refdes="GND1")

    S.connect(cid, [["V1", "+"], ["D1", "A"]], net="in")
    S.connect(cid, [["D1", "K"], ["R1", "1"]], net="out")
    S.connect(cid, [["V1", "-"], ["R1", "2"], ["GND1", "1"]], net="0")
    expect_err("二极管引脚不能用 '+' / '-' 这种别名",
               lambda: S.connect(cid, [["D1", "+"], ["V1", "+"]], net="x"),
               "PIN_NOT_FOUND", hint_sub="A, K")

    S.add_probe(cid, "in", name="P_in")
    st = S.add_probe(cid, "out", name="P_out")
    check("接完后 topology.supported=True",
          st["topology"]["supported"] is True, str(st["topology"].get("reason")))
    check("拓扑被判成 halfwave_rectifier",
          st["topology"]["kind"] == "halfwave_rectifier",
          str(st["topology"].get("kind")))
    check("complete=True", st["topology"]["complete"] is True)
    return cid


def t4_layout():
    print("\n[4] 布局模板与准入")
    t = L.analyze(ir_halfwave())
    check("kind = halfwave_rectifier", t.kind == "halfwave_rectifier", t.kind)
    check("out_net 是二极管之后那条线", t.out_net == "out", t.out_net)
    pos = L.plan(t)
    check("V1 在 (300, 300)", pos["V1"] == [300.0, 300.0], str(pos["V1"]))
    check("D1 在串联位 (660, 300)", pos["D1"] == [660.0, 300.0], str(pos["D1"]))
    check("R1 挂到地列 (780, 460)", pos["R1"] == [780.0, 460.0], str(pos["R1"]))
    check("GND 在 (300, 620)", pos["GND1"] == [300.0, 620.0], str(pos["GND1"]))
    check("模板表里有这一条（不是靠通用规则蒙对的）",
          "halfwave_rectifier" in L.KIND_TEMPLATES)
    check("两次 plan 结果一致（纯函数）", L.plan(L.analyze(ir_halfwave())) == pos)

    # ---- 拒绝姿势 ----
    def ir_diode_shunt():
        return build("d_shunt", [("V1", AC, 5.0), ("R1", R, 1000.0), ("D1", D, None),
                                 ("GND1", G, None)],
                     [("in", ["V1.1", "R1.1"]), ("n1", ["R1.2", "D1.A"]),
                      ("0", ["D1.K", "V1.2", "GND1.1"])])

    expect_err("二极管接到地（不是串联位）被拒",
               lambda: L.analyze(ir_diode_shunt()),
               "LAYOUT_UNSUPPORTED", reason="diode_template_unverified",
               hint_sub="V1 -> D1 -> R1 -> GND")

    def ir_two_diodes():
        return build("d2", [("V1", AC, 5.0), ("D1", D, None), ("D2", D, None),
                            ("R1", R, 1000.0), ("GND1", G, None)],
                     [("in", ["V1.1", "D1.A"]), ("n1", ["D1.K", "D2.A"]),
                      ("out", ["D2.K", "R1.1"]),
                      ("0", ["R1.2", "V1.2", "GND1.1"])])

    expect_err("两个二极管（全波/桥式没验过）被拒",
               lambda: L.analyze(ir_two_diodes()),
               "LAYOUT_UNSUPPORTED", reason="diode_multiple",
               hint_sub="全波")

    def ir_diode_cap():
        return build("d_cap", [("V1", AC, 5.0), ("D1", D, None), ("C1", C, 1e-6),
                               ("GND1", G, None)],
                     [("in", ["V1.1", "D1.A"]), ("out", ["D1.K", "C1.1"]),
                      ("0", ["C1.2", "V1.2", "GND1.1"])])

    expect_err("二极管 + 电容（峰值检波没验过）被拒",
               lambda: L.analyze(ir_diode_cap()),
               "LAYOUT_UNSUPPORTED", reason="diode_with_capacitor",
               hint_sub="电容")

    def ir_diode_second():
        return build("d_2nd", [("V1", AC, 5.0), ("R1", R, 1000.0), ("D1", D, None),
                               ("R2", R, 1000.0), ("GND1", G, None)],
                     [("in", ["V1.1", "R1.1"]), ("n1", ["R1.2", "D1.A"]),
                      ("out", ["D1.K", "R2.1"]),
                      ("0", ["R2.2", "V1.2", "GND1.1"])])

    expect_err("二极管不在电源之后第一个串联位，被拒",
               lambda: L.analyze(ir_diode_second()),
               "LAYOUT_UNSUPPORTED", reason="diode_template_unverified")


def t5_compile():
    print("\n[5] 编译：真的写出 .ms14，donor 来源与探针落点写进报告")
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, "halfwave.ms14")
    ir = ir_halfwave()
    ir.simulation.analysis = "transient"
    ir.simulation.start = 0.0
    ir.simulation.stop = 0.1
    ir.simulation.sample_rate = 100000.0
    for comp in ir.components:
        comp.position = L.plan(L.analyze(ir)).get(comp.refdes)

    rep = ir_compile.compile_ir(ir, out, verbose=False)
    check("产物存在", os.path.isfile(out), "%d 字节" % rep["bytes"])
    check("文件大小在合理区间（不是空壳）", rep["bytes"] > 20000, str(rep["bytes"]))

    by_ref = {c["refdes"]: c for c in rep["components"]}
    d = by_ref["D1"]
    check("D1 的 origin = registry", d["origin"] == "registry", str(d["origin"]))
    check("D1 的 donor 指向仓库里的样例",
          d["donor"] and "Fuente capacitiva final" in d["donor"], str(d["donor"]))
    check("D1 的 donor 位号记下来了", d["donor_refdes"] == "D2", str(d["donor_refdes"]))
    check("D1 实际引脚是 A/K", d["pins"] == ["A", "K"], str(d["pins"]))
    check("D1 的 SPICE 模板写进报告",
          d["spice_template"] == "d%p %tA %tK %m", str(d["spice_template"]))
    check("legacy 元件的 origin = legacy", by_ref["R1"]["origin"] == "legacy")
    check("legacy 元件没有 spice_template 字段值", by_ref["R1"]["spice_template"] is None)

    probes = {p["refdes"]: p for p in rep["probes"]}
    check("两个探针都放上了", set(probes) == {"P_in", "P_out"}, str(sorted(probes)))
    check("P_out 落在导线拐点上（不是引脚）",
          probes["P_out"]["at_pin"] is None, str(probes["P_out"]["at_pin"]))
    check("P_in 落在自己网络的引脚上（V1.+），不是别人的引脚",
          probes["P_in"]["at_pin"] in (["V1", "1"], None),
          str(probes["P_in"]["at_pin"]))

    # 读回来确认结构没坏
    import msbuild
    c2 = msbuild.load_donor(out)
    refs = {x["refdes"]: (x["family"], x["part"]) for x in c2.components()}
    check("回读能认出二极管", refs.get("D1") == ("DIODE", "1N4007G"), str(refs.get("D1")))
    pins = c2.pin_info([x for x in c2.components() if x["refdes"] == "D1"][0]["ciid"])
    check("回读引脚还是 A/K", set(pins) == {"A", "K"}, str(sorted(pins)))
    check("网络数对得上（in/out/0）", len(c2.nodes()) == 3, str(len(c2.nodes())))


def t6_regression():
    print("\n[6] 回归：一阶 RC 的拓扑判定与坐标没变")
    t = L.analyze(ir_rc())
    check("kind 仍是 bypass", t.kind == "bypass", t.kind)
    pos = L.plan(t)
    expect = {"V1": [300.0, 300.0], "R1": [660.0, 300.0],
              "C1": [780.0, 460.0], "GND1": [300.0, 620.0]}
    check("四个元件的坐标与 v0.7 完全一致", pos == expect, str(pos))
    check("RC 电路没有二极管，不走模板表", t.kind not in L.KIND_TEMPLATES)


def main():
    print("=" * 78)
    print("DIODE / 1N4007G 测试（不需要 Multisim）")
    print("registry: %s" % reg.REGISTRY_PATH)
    print("=" * 78)
    t1_registry()
    t2_ir_whitelist()
    cid = t3_session()
    t4_layout()
    t5_compile()
    t6_regression()
    try:
        S.delete_circuit(cid)
    except Exception:
        pass

    print("\n" + "=" * 78)
    print("结果：%d 通过 / %d 失败" % (npass, nfail))
    print("=" * 78)
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
