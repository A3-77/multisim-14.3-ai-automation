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
        check("网络是新建的", r["net"]["created"] is True)

        r = S.connect(cid, ["R1.2", "C1.1"])
        check("中间网络自动叫 n1", r["net"]["name"] == "n1", r["net"]["name"])

        r = S.connect(cid, [["C1", "2"], ["GND1", "1"]])
        check("含地的网络自动叫 '0'", r["net"]["name"] == "0", r["net"]["name"])

        # 追加引脚到已有网络（Agent 逐条描述连线的习惯）
        r = S.connect(cid, [["V1", "-"], ["GND1", "1"]], net="0")
        check("往已有网络追加引脚", r["net"]["created"] is False
              and set(r["net"]["pins"]) >= {"C1.2", "V1.2", "GND1.1"},
              str(r["net"]["pins"]))
        check("追加不产生重复引脚",
              len(r["net"]["pins"]) == len(set(r["net"]["pins"])),
              str(r["net"]["pins"]))

        r = S.connect(cid, [["C1", "2"]])
        check("单个引脚自动并回它所在的网络",
              r["net"]["name"] == "0" and r["net"]["created"] is False,
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
              and r["probe"]["name"] == "P1", str(r["probe"]))
        r = S.add_probe(cid, "R1.2")
        check("按引脚名加探针（自动找网络）", r["probe"]["net"] == "n1",
              str(r["probe"]))
        r = S.add_probe(cid, "0", name="GND_PROBE")
        check("显式命名", r["probe"]["name"] == "GND_PROBE", str(r["probe"]))

        expect_err("目标给元件名 -> 要求明确到引脚",
                   lambda: S.add_probe(cid, "R1"), "AMBIGUOUS_TARGET",
                   "两个引脚")
        expect_err("目标网络不存在",
                   lambda: S.add_probe(cid, "nope"), "NET_NOT_FOUND")
        expect_err("探针重名",
                   lambda: S.add_probe(cid, "in", name="P1"), "PROBE_DUPLICATE")

        # ---------------------------------------------------------------- 5
        print("\n[5] plan_layout：串联链坐标（与 v0.3.0/v0.5.0 实测一致）")
        ir, _meta = S._load(cid)
        pos = S.plan_layout(ir)
        check("源在 (300,300)", pos["V1"] == [300.0, 300.0], str(pos["V1"]))
        check("R1 在 (500,300)", pos["R1"] == [500.0, 300.0], str(pos["R1"]))
        check("C1 在 (700,400)", pos["C1"] == [700.0, 400.0], str(pos["C1"]))
        check("地在 (300,420)", pos["GND1"] == [300.0, 420.0], str(pos["GND1"]))

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
              S.plan_layout(ir2) == {"V1": [300.0, 300.0], "R1": [500.0, 300.0],
                                     "GND1": [300.0, 420.0]},
              str(S.plan_layout(ir2)))
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
        expect_err("并联 -> LAYOUT_UNSUPPORTED",
                   lambda: S.plan_layout(irb), "LAYOUT_UNSUPPORTED", "串联链")

        n = S.create_circuit("no_ground")
        nid = n["circuit_id"]
        S.add_component(nid, "POWER_SOURCES", "DC_POWER", "V1", value=5.0)
        S.add_component(nid, "RESISTOR", "RESISTOR_VIRTUAL", "R1", value=1000.0)
        S.connect(nid, [["V1", "+"], ["R1", "1"]])
        S.connect(nid, [["V1", "-"], ["R1", "2"]])
        irn, _mn = S._load(nid)
        expect_err("没有地 -> NO_GROUND", lambda: S.plan_layout(irn), "NO_GROUND")

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

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("-" * 80)
    print("总计 %d 项通过，%d 项失败 => %s"
          % (npass, nfail, "PASS" if nfail == 0 else "FAIL"))
    print("-" * 80)
    return 0 if nfail == 0 else 1


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
