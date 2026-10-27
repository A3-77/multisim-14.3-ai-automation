# -*- coding: utf-8 -*-
"""circuit_session 的纯逻辑测试（不需要 Multisim，任意位数 Python）。

覆盖：
    * create_circuit / add_component 的语义参数映射与错误
    * connect 的自动命名、合并、引脚冲突
    * add_probe 的目标解析（网络名 / 引脚 / 元件）、上限
    * plan_layout 对 RC 低通与直流电路的坐标
    * 非串联链拓扑必须明确报错（不猜布局）

跑法：
    python tools/test_mcp_session.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import circuit_session as S   # noqa: E402

npass = 0
nfail = 0


def check(name, cond, detail=""):
    global npass, nfail
    if cond:
        npass += 1
        print("  %-52s OK   %s" % (name, detail))
    else:
        nfail += 1
        print("  %-52s FAIL %s" % (name, detail))


def expect_err(name, fn, code, hint_sub=None):
    try:
        fn()
    except S.SessionError as e:
        ok = (e.code == code)
        if ok and hint_sub:
            blob = "%s %s" % (e.hint or "", e.message or "")
            ok = hint_sub in blob
        check(name, ok, "%s / %s" % (e.code, e.message))
        return e
    except Exception as e:
        check(name, False, "抛了别的异常：%r" % (e,))
        return None
    check(name, False, "没有报错")
    return None


def main():
    tmp = tempfile.mkdtemp(prefix="mcp_sess_")
    S.SESS_ROOT = tmp
    print("=" * 80)
    print("circuit_session 纯逻辑测试（临时目录 %s）" % tmp)
    print("=" * 80)

    try:
        # ---------------------------------------------------------------- 1
        print("\n[1] create_circuit")
        c = S.create_circuit("rc_lowpass")
        cid = c["circuit_id"]
        check("返回 circuit_id", bool(cid) and cid.startswith("c-"), cid)
        check("初始为空", c["counts"] == {"components": 0, "nets": 0, "probes": 0},
              str(c["counts"]))
        check("name 保留", c["name"] == "rc_lowpass", c["name"])
        expect_err("不存在的 circuit_id", lambda: S.get_circuit("c-deadbeef00"),
                   "CIRCUIT_NOT_FOUND")
        expect_err("非法 circuit_id（防路径穿越）",
                   lambda: S.get_circuit("../../etc"), "BAD_CIRCUIT_ID")

        # ---------------------------------------------------------------- 2
        print("\n[2] add_component：语义参数")
        r = S.add_component(cid, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                            value=1.0, frequency=1000.0)
        v1 = r["component"]
        check("AC_VOLTAGE 幅值 1 V", v1["value"] == 1.0, str(v1["value"]))
        check("frequency 翻成 IR 参数（不暴露序号）",
              v1.get("parameters") == {"frequency": 1000.0},
              str(v1.get("parameters")))
        check("引脚列表给出来", v1["pins"] == ["1", "2"], str(v1["pins"]))
        check("正负别名给出来", v1["aliases"] == {"+": "1", "-": "2"},
              str(v1["aliases"]))

        r = S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        check("电阻 1000 Ω", r["component"]["value"] == 1000.0)
        r = S.add_component(cid, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=159e-9)
        check("电容 159 nF", abs(r["component"]["value"] - 159e-9) < 1e-20)
        r = S.add_component(cid, "POWER_SOURCES", "GROUND", "GND1")
        check("地不需要 value", r["component"]["value"] is None)

        expect_err("refdes 重复",
                   lambda: S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL",
                                           "R1", value=1.0),
                   "DUPLICATE_REFDES")
        expect_err("白名单外元件",
                   lambda: S.add_component(cid, "INDUCTOR", "INDUCTOR_VIRTUAL",
                                           "L1", value=1e-3),
                   "UNKNOWN_COMPONENT_TYPE", "第一版只开放")
        expect_err("AC_VOLTAGE 缺 frequency",
                   lambda: S.add_component(cid, "SIGNAL_VOLTAGE_SOURCES",
                                           "AC_VOLTAGE", "V2", value=1.0),
                   "MISSING_PARAMETER", "frequency")
        expect_err("电阻缺 value",
                   lambda: S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL",
                                           "R9"),
                   "MISSING_VALUE", "resistance")
        expect_err("value 为负",
                   lambda: S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL",
                                           "R8", value=-5),
                   "BAD_ARGUMENT")
        expect_err("地不接受 value",
                   lambda: S.add_component(cid, "POWER_SOURCES", "GROUND",
                                           "GND2", value=5),
                   "BAD_ARGUMENT")

        r = S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL", value=470.0)
        check("不传 refdes 自动编号", r["component"]["refdes"] == "R2",
              r["component"]["refdes"])

        # ---------------------------------------------------------------- 3
        print("\n[3] connect：自动命名 / 合并 / 冲突")
        r = S.connect(cid, [["V1", "+"], ["R1", "1"]])
        check("含电源正极的网络自动叫 'in'", r["net"]["name"] == "in",
              r["net"]["name"])
        check("网络是新建的", r["created"] is True)

        r = S.connect(cid, ["R1.2", "C1.1"])
        check("中间网络自动叫 n1", r["net"]["name"] == "n1", r["net"]["name"])

        r = S.connect(cid, [["C1", "2"], ["GND1", "1"]])
        check("含地的网络自动叫 '0'", r["net"]["name"] == "0", r["net"]["name"])

        # 追加引脚到已有网络（Agent 逐条描述连线的习惯）
        r = S.connect(cid, [["V1", "-"], ["GND1", "1"]], net="0")
        check("往已有网络追加引脚", r["created"] is False
              and set(r["net"]["pins"]) >= {"C1.2", "V1.2", "GND1.1"},
              str(r["net"]["pins"]))
        check("追加不产生重复引脚",
              len(r["net"]["pins"]) == len(set(r["net"]["pins"])),
              str(r["net"]["pins"]))

        r = S.connect(cid, [["C1", "2"]])
        check("单个引脚自动并回它所在的网络",
              r["net"]["name"] == "0" and r["created"] is False,
              str(r["net"]))

        expect_err("引脚已属于别的网络",
                   lambda: S.connect(cid, [["R1", "2"], ["V1", "+"]]),
                   "PIN_ALREADY_CONNECTED", "同一个引脚")
        expect_err("元件不存在",
                   lambda: S.connect(cid, [["R7", "1"], ["R1", "1"]]),
                   "COMPONENT_NOT_FOUND")
        expect_err("引脚不存在",
                   lambda: S.connect(cid, [["R1", "3"], ["V1", "+"]]),
                   "PIN_NOT_FOUND")
        expect_err("新建网络只有 1 个引脚",
                   lambda: S.connect(cid, [["R2", "1"]], net="solo"),
                   "BAD_ARGUMENT")

        # ---------------------------------------------------------------- 4
        print("\n[4] add_probe：目标解析")
        r = S.add_probe(cid, "in")
        check("按网络名加探针", r["probe"]["net"] == "in"
              and r["probe"]["probe_id"] == "P1", str(r["probe"]))
        r = S.add_probe(cid, "R1.2")
        check("按引脚名加探针（自动找网络）", r["probe"]["net"] == "n1",
              str(r["probe"]))
        r = S.add_probe(cid, "0", name="GND_PROBE")
        check("显式命名", r["probe"]["probe_id"] == "GND_PROBE", str(r["probe"]))

        expect_err("目标给元件名 -> 要求明确到引脚",
                   lambda: S.add_probe(cid, "R1"), "AMBIGUOUS_TARGET",
                   "两个引脚")
        expect_err("目标网络不存在",
                   lambda: S.add_probe(cid, "nope"), "NET_NOT_FOUND")
        expect_err("探针重名",
                   lambda: S.add_probe(cid, "in", name="P1"), "PROBE_DUPLICATE")

        # ---------------------------------------------------------------- 5
        print("\n[5] plan_layout：一阶 RC 的坐标（拓扑网格，v0.7.0 起）")
        # 注意：cid 里有个自动编号出来的 R2（470Ω）没接线。拓扑层会把它判成
        # island —— 这是有意的（见 [8]）。所以坐标用一条干净的一阶 RC 来验。
        lay = S.create_circuit("layout_rc")
        lid = lay["circuit_id"]
        S.add_component(lid, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                        value=1.0, frequency=1000.0)
        S.add_component(lid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(lid, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=159e-9)
        S.add_component(lid, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(lid, [["V1", "+"], ["R1", "1"]])
        S.connect(lid, [["R1", "2"], ["C1", "1"]])
        S.connect(lid, [["C1", "2"], ["V1", "-"], ["GND1", "1"]])
        irl, _ml = S._load(lid)
        pos = S.plan_layout(irl)
        check("源在 (300,300)", pos["V1"] == [300.0, 300.0], str(pos["V1"]))
        check("R1 在 (660,300)（第 0 级串联）",
              pos["R1"] == [660.0, 300.0], str(pos["R1"]))
        check("C1 在 (780,460)（第 1 级到地）",
              pos["C1"] == [780.0, 460.0], str(pos["C1"]))
        check("地在 (300,620)", pos["GND1"] == [300.0, 620.0], str(pos["GND1"]))
        topo = S.topology_of(irl)
        check("拓扑识别为一阶 RC（bypass）", topo.kind == "bypass", topo.kind)
        check("输出网是 C1 所在节点", topo.out_net == "n1", topo.out_net)

        # ---------------------------------------------------------------- 6
        print("\n[6] 直流电路：同一套接口，不加任何特殊分支")
        d = S.create_circuit("dc_5v")
        did = d["circuit_id"]
        S.add_component(did, "POWER_SOURCES", "DC_POWER", "V1", value=5.0)
        S.add_component(did, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(did, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(did, [["V1", "+"], ["R1", "1"]])
        S.connect(did, [["R1", "2"], ["V1", "-"], ["GND1", "1"]])
        S.add_probe(did, "in")
        S.add_probe(did, "0")
        ir2, _m2 = S._load(did)
        check("直流拓扑也走同一套布局",
              S.plan_layout(ir2) == {"V1": [300.0, 300.0], "R1": [540.0, 460.0],
                                     "GND1": [300.0, 620.0]},
              str(S.plan_layout(ir2)))
        check("直流拓扑识别为 shunt_load",
              S.topology_of(ir2).kind == "shunt_load",
              S.topology_of(ir2).kind)
        check("默认分析类型 = dc", S._default_analysis(ir2) == "dc",
              S._default_analysis(ir2))
        check("DC 源的 '+' 别名映射到引脚 1",
              S._norm_pin(ir2.component("V1"), "+") == "1")

        # ---------------------------------------------------------------- 7
        print("\n[7] 分析类型 / 源类型匹配（错误要能指导 Agent 改）")
        ir3, _m3 = S._load(cid)
        expect_err("AC_VOLTAGE 不支持 dc",
                   lambda: S._check_analysis(ir3, "dc"),
                   "ANALYSIS_NOT_SUPPORTED", "transient")
        e = None
        try:
            S._check_analysis(ir3, "dc")
        except S.SessionError as ex:
            e = ex
        check("错误里带 supported 列表",
              e is not None and e.context.get("supported") == ["transient"],
              str(e.context if e else None))
        check("AC 默认 transient", S._default_analysis(ir3) == "transient")

        # ---------------------------------------------------------------- 8
        print("\n[8] 拓扑不支持时必须报错，不能硬排坐标")
        b = S.create_circuit("parallel")
        bid = b["circuit_id"]
        S.add_component(bid, "POWER_SOURCES", "DC_POWER", "V1", value=5.0)
        S.add_component(bid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(bid, "RESISTOR", "RESISTOR_VIRTUAL", "R2", value=1000.0)
        S.add_component(bid, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(bid, [["V1", "+"], ["R1", "1"], ["R2", "1"]])
        S.connect(bid, [["R1", "2"], ["R2", "2"], ["V1", "-"], ["GND1", "1"]])
        irb, _mb = S._load(bid)
        e = expect_err("并联到地 -> LAYOUT_UNSUPPORTED",
                       lambda: S.plan_layout(irb), "LAYOUT_UNSUPPORTED",
                       "并联到地")
        check("  错误带 reason=parallel_shunt",
              e is not None and e.context.get("reason") == "parallel_shunt",
              str(e.context if e else None))

        # 悬空元件（cid 里那个没接线的 R2）也必须被拓扑层拦住
        irc, _mc = S._load(cid)
        e = expect_err("有元件没接线 -> island",
                       lambda: S.plan_layout(irc), "LAYOUT_UNSUPPORTED",
                       "不连通")
        check("  错误带 reason=island",
              e is not None and e.context.get("reason") == "island",
              str(e.context if e else None))

        n = S.create_circuit("no_ground")
        nid = n["circuit_id"]
        S.add_component(nid, "POWER_SOURCES", "DC_POWER", "V1", value=5.0)
        S.add_component(nid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.connect(nid, [["V1", "+"], ["R1", "1"]])
        S.connect(nid, [["V1", "-"], ["R1", "2"]])
        irn, _mn = S._load(nid)
        expect_err("没有地 -> NO_GROUND", lambda: S.plan_layout(irn), "NO_GROUND")

        # ---------------------------------------------------------------- 8b
        print("\n[8b] P2：三个具名模板 + 二阶梯形都能过（v0.7.0 的核心）")

        # 分压：V1 - R1 - n1 - R2 - 0，探针在 n1
        dv = S.create_circuit("divider")
        dvid = dv["circuit_id"]
        S.add_component(dvid, "POWER_SOURCES", "DC_POWER", "V1", value=10.0)
        S.add_component(dvid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(dvid, "RESISTOR", "RESISTOR_VIRTUAL", "R2", value=1000.0)
        S.add_component(dvid, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(dvid, [["V1", "+"], ["R1", "1"]])
        S.connect(dvid, [["R1", "2"], ["R2", "1"]])
        S.connect(dvid, [["R2", "2"], ["V1", "-"], ["GND1", "1"]])
        S.add_probe(dvid, "n1")
        t = S.topology_of(S._load(dvid)[0])
        check("分压 -> divider", t.kind == "divider", t.kind)
        check("  输出网 = n1", t.out_net == "n1", t.out_net)
        check("  两个电阻都摆上了",
              set(S.plan_layout(S._load(dvid)[0])) == {"V1", "R1", "R2", "GND1"})

        # 二阶 RC 梯形：in - R1 - n1(-C1) - R2 - n2(-C2) - 0
        ld = S.create_circuit("rc2")
        ld_id = ld["circuit_id"]
        S.add_component(ld_id, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                        value=1.0, frequency=1000.0)
        S.add_component(ld_id, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=10000.0)
        S.add_component(ld_id, "RESISTOR", "RESISTOR_VIRTUAL", "R2", value=10000.0)
        S.add_component(ld_id, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=8.2e-9)
        S.add_component(ld_id, "CAPACITOR", "CAPACITOR_VIRTUAL", "C2", value=8.2e-9)
        S.add_component(ld_id, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(ld_id, [["V1", "+"], ["R1", "1"]])
        S.connect(ld_id, [["R1", "2"], ["C1", "1"], ["R2", "1"]])
        S.connect(ld_id, [["R2", "2"], ["C2", "1"]])
        S.connect(ld_id, [["C1", "2"], ["C2", "2"], ["V1", "-"], ["GND1", "1"]])
        S.add_probe(ld_id, "in")
        S.add_probe(ld_id, "n2")
        irl2, _ml2 = S._load(ld_id)
        t = S.topology_of(irl2)
        check("二阶 RC -> ladder", t.kind == "ladder", t.kind)
        check("  2 级主干 / 2 个到地", (t.n_series, t.n_shunt) == (2, 2),
              "%d/%d" % (t.n_series, t.n_shunt))
        check("  三引脚节点 n1 是正常级",
              [s.net for s in t.stages] == ["in", "n1", "n2"],
              str([s.net for s in t.stages]))
        check("  输出网 = n2", t.out_net == "n2", t.out_net)
        pos2 = S.plan_layout(irl2)
        check("  6 个元件都有坐标", len(pos2) == 6, str(sorted(pos2)))
        check("  串联向右递进", pos2["R1"][0] < pos2["R2"][0],
              "%g < %g" % (pos2["R1"][0], pos2["R2"][0]))
        check("  并联挂在下方",
              pos2["C1"][1] > pos2["R1"][1] and pos2["C2"][1] > pos2["R2"][1])
        snap = S.get_circuit(ld_id)
        check("get_circuit 里带 topology",
              snap["topology"]["kind"] == "ladder"
              and snap["topology"]["supported"] is True,
              str(snap["topology"].get("kind")))
        check("未搭完的电路 topology 给出原因而不是报错",
              S.get_circuit(cid)["topology"]["supported"] is False
              and S.get_circuit(cid)["topology"]["reason"] == "island",
              str(S.get_circuit(cid)["topology"].get("reason")))

        # ---------------------------------------------------------------- 9
        print("\n[9] 探针上限 9")
        p = S.create_circuit("probes")
        pid = p["circuit_id"]
        S.add_component(pid, "POWER_SOURCES", "DC_POWER", "V1", value=5.0)
        S.add_component(pid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(pid, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(pid, [["V1", "+"], ["R1", "1"]])
        S.connect(pid, [["R1", "2"], ["V1", "-"], ["GND1", "1"]])
        for i in range(1, 10):
            S.add_probe(pid, "in", name="PX%d" % i)
        irp, _mp = S._load(pid)
        check("9 个探针允许", len(irp.probes) == 9, str(len(irp.probes)))
        expect_err("第 10 个探针 -> PROBE_LIMIT",
                   lambda: S.add_probe(pid, "in"), "PROBE_LIMIT", "9")

        # ---------------------------------------------------------------- 10
        print("\n[10] simulate 的前置检查（不真的跑 COM）")
        expect_err("没有探针就仿真",
                   lambda: S.simulate(_fresh_no_probe(tmp)),
                   "NO_PROBE")

        # ---------------------------------------------------------------- 11
        print("\n[11] 会话持久化：重新读回来内容一致")
        again = S.get_circuit(cid)
        check("元件数 5", again["counts"]["components"] == 5, str(again["counts"]))
        check("网络数 3", again["counts"]["nets"] == 3, str(again["counts"]))
        check("探针数 3", again["counts"]["probes"] == 3, str(again["counts"]))
        check("元件顺序保持", [c["refdes"] for c in again["components"]]
              == ["V1", "R1", "C1", "GND1", "R2"],
              str([c["refdes"] for c in again["components"]]))
        check("list_sessions 能列出来",
              any(s["id"] == cid for s in S.list_sessions()))

        S.delete_circuit(pid)
        check("delete_circuit 生效",
              not os.path.isdir(os.path.join(tmp, pid)))

        # ---------------------------------------------------------------- 12
        print("\n[12] v0.6.2：parameters 只认语义名，params 直接拒绝")
        pc = S.create_circuit("params")
        pcid = pc["circuit_id"]
        r = S.add_component(pcid, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                            value=2.0, parameters={"frequency": 2000.0})
        check("parameters 写法生效",
              r["component"]["parameters"] == {"frequency": 2000.0},
              str(r["component"]["parameters"]))
        check("component 带 value_name / value_unit",
              (r["component"]["value_name"], r["component"]["value_unit"])
              == ("amplitude", "V"),
              str((r["component"]["value_name"], r["component"]["value_unit"])))
        check("没有额外参数时 parameters 是 {}（不是缺失）",
              "parameters" in S.add_component(
                  pcid, "RESISTOR", "RESISTOR_VIRTUAL", "R1",
                  value=1000.0)["component"],
              "字段存在")
        expect_err("params（数字序号）被拒绝",
                   lambda: S.add_component(pcid, "SIGNAL_VOLTAGE_SOURCES",
                                           "AC_VOLTAGE", "V4", value=1.0,
                                           params={"5": 1000}),
                   "UNSUPPORTED_PARAMETER", "parameters")
        expect_err("未知语义参数 -> 列出可用参数",
                   lambda: S.add_component(pcid, "SIGNAL_VOLTAGE_SOURCES",
                                           "AC_VOLTAGE", "V5", value=1.0,
                                           parameters={"freq": 1000}),
                   "UNKNOWN_PARAMETER", "frequency")
        expect_err("parameters 与 frequency 同时给 -> 不猜",
                   lambda: S.add_component(pcid, "SIGNAL_VOLTAGE_SOURCES",
                                           "AC_VOLTAGE", "V6", value=1.0,
                                           parameters={"frequency": 1000},
                                           frequency=2000),
                   "BAD_ARGUMENT")
        e2 = None
        try:
            S.add_component(pcid, "RESISTOR", "RESISTOR_VIRTUAL", "R8", value=-5)
        except S.SessionError as ex:
            e2 = ex
        check("错误 context 不再嵌套一层 context",
              e2 is not None and "context" not in e2.context,
              str(e2.context if e2 else None))

        # ---------------------------------------------------------------- 13
        print("\n[13] v0.6.2：探针身份统一为 probe_id")
        gc = S.get_circuit(cid)
        pr0 = gc["probes"][0]
        check("probes[] 是固定 5 字段",
              set(pr0) == {"probe_id", "label", "output", "net", "kind"},
              str(sorted(pr0)))
        check("没仿真时 label / output 是 None（字段仍在）",
              pr0["label"] is None and pr0["output"] is None, str(pr0))
        check("component 字段固定 9 项",
              set(gc["components"][0]) == {
                  "refdes", "family", "part", "value", "value_name",
                  "value_unit", "parameters", "pins", "aliases"},
              str(sorted(gc["components"][0])))

        sid = _fake_sim(cid)
        w = S.get_waveform(sid)
        check("get_waveform.channels 用 probe_id 作键",
              set(w["channels"]) == {"P1", "P2"}, str(sorted(w["channels"])))
        ch = w["channels"]["P1"]
        check("通道带 label / output / net（只读旁证）",
              (ch["label"], ch["output"], ch["net"]) == ("探针1", "V(探针1)", "in"),
              str({k: ch[k] for k in ("label", "output", "net")}))
        check("probe_id 过滤只留一个通道",
              set(S.get_waveform(sid, probe_id="P2")["channels"]) == {"P2"})

        e = expect_err("传 Multisim 输出名 -> hint 直接给出正确 probe_id",
                       lambda: S.get_waveform(sid, probe_id="V(探针1)"),
                       "PROBE_NOT_FOUND", "probe_id 是 'P1'")
        check("错误里带 matched 字段",
              e is not None and e.context.get("matched") == "P1",
              str(e.context if e else None))
        expect_err("传 Multisim 显示名 -> 同样纠正",
                   lambda: S.get_waveform(sid, probe_id="探针1"),
                   "PROBE_NOT_FOUND", "probe_id 是 'P1'")
        expect_err("measure 的 probe_id 是同一套语义",
                   lambda: S.measure(sid, probe_id="V(探针2)"),
                   "PROBE_NOT_FOUND", "probe_id 是 'P2'")
        expect_err("measure 的 probe_id 不存在",
                   lambda: S.measure(sid, probe_id="P9"),
                   "PROBE_NOT_FOUND", "P1")

        # 兼容 v0.6.0/v0.6.1 写的旧记录（探针键叫 name）
        legacy = _fake_sim(cid, legacy=True)
        check("旧格式仿真记录仍可读（probes[].name）",
              set(S.get_waveform(legacy)["channels"]) == {"P1", "P2"},
              str(sorted(S.get_waveform(legacy)["channels"])))

        # ---------------------------------------------------------------- 14
        print("\n[14] v0.6.2：simulate 的 timeout 参数校验（不真的跑 COM）")
        expect_err("timeout 非数字",
                   lambda: S.simulate(cid, timeout="abc"), "BAD_ARGUMENT")
        expect_err("timeout <= 0",
                   lambda: S.simulate(cid, timeout=0), "BAD_ARGUMENT")

        # ---------------------------------------------------------------- 15
        print("\n[15] v0.8.0：gain 的方向由拓扑决定，不由探针顺序决定")
        c2 = S.create_circuit("pairing")
        cid2 = c2["circuit_id"]
        S.add_component(cid2, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                        value=1.0, frequency=1000.0)
        S.add_component(cid2, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(cid2, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=100e-9)
        S.add_component(cid2, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(cid2, [["V1", "+"], ["R1", "1"]], net="in")
        S.connect(cid2, [["R1", "2"], ["C1", "1"]], net="out")
        S.connect(cid2, [["C1", "2"], ["V1", "-"], ["GND1", "1"]], net="0")
        # **先加输出探针、后加输入探针** —— v0.7.0 在这个顺序下会把 gain 算反
        S.add_probe(cid2, "out", name="P_out")
        S.add_probe(cid2, "in", name="P_in")

        ir2, _meta2 = S._load(cid2)
        topo2 = S._topology(ir2)
        chans2 = {"P_out": {"net": "out", "amp": 0.5},
                  "P_in": {"net": "in", "amp": 1.0}}
        i_pid, o_pid, how = S._pair_probes(chans2, ["P_out", "P_in"], topo2, ir2)
        check("按拓扑配对（不看添加顺序）", how == "topology", how)
        check("输入 = 源正极网络上的探针", i_pid == "P_in", str(i_pid))
        check("输出 = topology.out_net 上的探针", o_pid == "P_out", str(o_pid))

        i2, o2, how2 = S._pair_probes(chans2, ["P_in", "P_out"], topo2, ir2)
        check("把添加顺序倒过来，结论不变",
              (i2, o2, how2) == ("P_in", "P_out", "topology"),
              "%s / %s / %s" % (i2, o2, how2))

        _i3, _o3, how3 = S._pair_probes({"P_out": chans2["P_out"]},
                                        ["P_out"], topo2, ir2)
        check("只有一个探针时退回 single", how3 == "single", how3)

        chans_bad = {"P_a": {"net": "x"}, "P_b": {"net": "y"}}
        _i4, _o4, how4 = S._pair_probes(chans_bad, ["P_a", "P_b"], topo2, ir2)
        check("拓扑判断不出时退回 probe_order（并会在 notes 里说明）",
              how4 == "probe_order", how4)

        # ---------------------------------------------------------------- 16
        print("\n[16] v0.8.0：topology 的 supported 与 complete 是两件事")
        c3 = S.create_circuit("incomplete")
        cid3 = c3["circuit_id"]
        S.add_component(cid3, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                        value=1.0, frequency=1000.0)
        S.add_component(cid3, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(cid3, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=100e-9)
        S.add_component(cid3, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(cid3, [["V1", "+"], ["R1", "1"]], net="in")
        S.connect(cid3, [["R1", "2"], ["C1", "1"]], net="out")
        S.connect(cid3, [["V1", "-"], ["GND1", "1"]], net="0")   # C1.2 还悬空
        t3 = S.get_circuit(cid3)["topology"]
        check("有引脚悬空时布局不认（supported=false）",
              t3.get("supported") is False, str(t3))
        check("电路没接完（complete=false）", t3.get("complete") is False, str(t3))
        check("issues 点名悬空的引脚",
              any("C1.2" in s for s in (t3.get("issues") or [])),
              str(t3.get("issues")))

        # 接完线之后：拓扑认了，但没探针仍然算没就绪
        S.connect(cid3, [["C1", "2"], ["V1", "-"], ["GND1", "1"]], net="0")
        t4 = S.get_circuit(cid3)["topology"]
        check("接完线后 supported=true", t4.get("supported") is True, str(t4))
        check("没有探针时 complete 仍为 false", t4.get("complete") is False, str(t4))
        S.add_probe(cid3, "out", name="P1")
        t5 = S.get_circuit(cid3)["topology"]
        check("有探针后 complete=true", t5.get("complete") is True, str(t5))

        # 能力边界 vs 接线问题：parallel_shunt 是"接完了但不会摆"
        c4 = S.create_circuit("par")
        cid4 = c4["circuit_id"]
        S.add_component(cid4, "SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                        value=1.0, frequency=1000.0)
        S.add_component(cid4, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.add_component(cid4, "RESISTOR", "RESISTOR_VIRTUAL", "R2", value=10000.0)
        S.add_component(cid4, "CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=10e-9)
        S.add_component(cid4, "POWER_SOURCES", "GROUND", "GND1")
        S.connect(cid4, [["V1", "+"], ["R1", "1"]], net="in")
        S.connect(cid4, [["R1", "2"], ["R2", "1"], ["C1", "1"]], net="out")
        S.connect(cid4, [["R2", "2"], ["C1", "2"], ["V1", "-"], ["GND1", "1"]],
                 net="0")
        S.add_probe(cid4, "out", name="P1")
        t6 = S.get_circuit(cid4)["topology"]
        check("parallel_shunt：supported=false",
              t6.get("supported") is False, str(t6))
        check("parallel_shunt：但 complete=true（电路是接完的）",
              t6.get("complete") is True, str(t6))
        check("reason 指出是哪一类拓扑问题",
              t6.get("reason") == "parallel_shunt", str(t6.get("reason")))

        # ---------------------------------------------------------------- 17
        print("\n[17] v0.8.0：simulate 的 start / stop 校验（不真的跑 COM）")
        expect_err("start 为负", lambda: S.simulate(cid, start=-1e-3),
                   "BAD_ARGUMENT")
        expect_err("start >= stop", lambda: S.simulate(cid, start=5e-3, stop=1e-3),
                   "BAD_ARGUMENT", "必须小于")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("-" * 80)
    print("总计 %d 项通过，%d 项失败 => %s"
          % (npass, nfail, "PASS" if nfail == 0 else "FAIL"))
    print("-" * 80)
    return 0 if nfail == 0 else 1


def _fake_sim(cid, legacy=False):
    """造一个仿真记录 + CSV，专测 measure / get_waveform 的通道语义。

    不需要 Multisim：探针过滤和 get_waveform 的全部逻辑都在正弦拟合之前，
    所以 64 位 Python 也能跑。`legacy=True` 时探针键写成 v0.6.1 的 `name`，
    用来验证旧记录仍然读得出来。
    """
    import csv as _csv
    import json as _json

    sims = os.path.join(S.SESS_ROOT, cid, "sims")
    os.makedirs(sims, exist_ok=True)
    sid = "s-0f1e2d3c4b" if not legacy else "s-1a2b3c4d5e"
    csv_path = os.path.join(sims, "%s.csv" % sid)
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["t", "V(探针1)", "V(探针2)"])
        for i in range(100):
            w.writerow(["%.9g" % (i * 5e-6), "%.9g" % (1.0 - i * 0.01),
                        "%.9g" % (0.5 - i * 0.001)])

    probes = [
        {"label": "探针1", "output": "V(探针1)", "net": "in", "probe_id": "P1"},
        {"label": "探针2", "output": "V(探针2)", "net": "n1", "probe_id": "P2"},
    ]
    if legacy:
        probes = [{"name": p["probe_id"], "output": p["output"], "net": p["net"]}
                  for p in probes]

    rec = {
        "sim_id": sid, "circuit_id": cid, "analysis": "transient",
        "status": "ok", "created": "2026-01-01T00:00:00",
        "outputs": ["V(探针1)", "V(探针2)"], "probes": probes,
        "sample_rate": 200000.0, "stop": 5e-4, "n": 100,
        "ir_snapshot": os.path.join(S.SESS_ROOT, cid, "circuit.ir.json"),
        "waveform": csv_path,
        "summary": {}, "timing": {}, "compile": {},
    }
    with open(os.path.join(sims, "%s.json" % sid), "w", encoding="utf-8") as fh:
        _json.dump(rec, fh, ensure_ascii=False, indent=2)
    return sid


def _fresh_no_probe(tmp):
    c = S.create_circuit("no_probe")
    cid = c["circuit_id"]
    S.add_component(cid, "POWER_SOURCES", "DC_POWER", "V1", value=5.0)
    S.add_component(cid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
    S.add_component(cid, "POWER_SOURCES", "GROUND", "GND1")
    S.connect(cid, [["V1", "+"], ["R1", "1"]])
    S.connect(cid, [["R1", "2"], ["V1", "-"], ["GND1", "1"]])
    return cid


if __name__ == "__main__":
    sys.exit(main())
