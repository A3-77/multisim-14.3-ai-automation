# -*- coding: utf-8 -*-
"""中文 -> Circuit IR 的解析测试。

两类用例：
    正向  一句话必须解析成**指定的** IR（不是"能跑就行"，是字段逐个对）
    反向  每种不支持的输入都必须**报错**，且错误信息里说清缺什么

不需要 Multisim，纯 Python。

用法：
    python tools/test_nl2ir.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nl2ir  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "rc_lowpass.ir.json")
fails = 0
npass = 0


def check(name, cond, detail=""):
    global fails, npass
    if cond:
        npass += 1
        print("  %-56s OK%s" % (name, ("  " + detail) if detail else ""))
    else:
        fails += 1
        print("  %-56s FAIL%s" % (name, ("  " + detail) if detail else ""))


def canon(d):
    """语义等价比较：去掉 None / 空 dict / 空 list / name，键顺序无关。"""
    d = copy.deepcopy(d)

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()
                    if v is not None and v != {} and v != [] and k != "name"}
        if isinstance(o, list):
            return [clean(x) for x in o]
        return o

    return clean(d)


def ok(text):
    ir, rep = nl2ir.parse(text)
    errs = ir.validate()
    check("  解析结果通过 validate()", not errs, str(errs) if errs else "")
    return ir, rep


def bad(text, want):
    try:
        nl2ir.parse(text)
    except nl2ir.NLParseError as e:
        hit = [i for i in e.issues if want in i]
        check("拒绝：" + want, bool(hit), hit[0] if hit else ("实际：%s" % e.issues))
        return
    check("拒绝：" + want, False, "居然解析成功了")


print("=" * 80)
print("中文 -> Circuit IR 解析测试")
print("=" * 80)

# ---------------------------------------------------------------- 正向
print("\n[正向] 验收句必须还原成 v0.3.0 的手工 IR")
ACCEPT = ("创建一个 1V、1kHz 的正弦源，经过 1kΩ 电阻后接一个 159nF 电容到地，"
          "在输入节点和输出节点各放一个电压探针，做瞬态分析。")
ir, rep = ok(ACCEPT)
base = json.load(open(EXAMPLE, encoding="utf-8"))
check("与 examples/rc_lowpass.ir.json 语义完全一致",
      canon(ir.to_dict()) == canon(base),
      "" if canon(ir.to_dict()) == canon(base) else json.dumps(canon(ir.to_dict()),
                                                             ensure_ascii=False)[:200])
check("元件数 4（源 + R + C + 地）", len(ir.components) == 4, str(len(ir.components)))
check("网络 in/out/0", [n.name for n in ir.nets] == ["in", "out", "0"],
      str([n.name for n in ir.nets]))
check("两个探针分别在 in / out", [p.net for p in ir.probes] == ["in", "out"],
      str([p.net for p in ir.probes]))
check("仿真 6 个周期 = 6 ms", abs(ir.simulation.stop - 0.006) < 1e-12,
      "%g" % ir.simulation.stop)
check("采样率 = 200 × 1 kHz", abs(ir.simulation.sample_rate - 200000.0) < 1e-9,
      "%g" % ir.simulation.sample_rate)

print("\n[正向] 语序 / 中文单位 / 显式位号")
ir, rep = ok("1V 1kHz 正弦源，串联 1kΩ 电阻和 159nF 电容，接地，在输出节点放一个电压探针。")
check("'串联...和...接地' 也能排成链",
      [c.refdes for c in ir.components] == ["V1", "R1", "C1", "GND1"],
      str([c.refdes for c in ir.components]))
check("只声明输出探针 → 1 个探针", len(ir.probes) == 1, str(len(ir.probes)))

ir, rep = ok("新建一个 1 伏、1 千赫的正弦源，经过 1 千欧的电阻，再接到 159 纳法的电容，"
             "最后接地；在输出端放一个电压探针。")
check("中文单位 伏/千赫/千欧/纳法",
      abs(ir.component("V1").value - 1.0) < 1e-12
      and abs(ir.component("V1").params[5] - 1000.0) < 1e-9
      and abs(ir.component("R1").value - 1000.0) < 1e-9
      and abs(ir.component("C1").value - 159e-9) < 1e-15,
      "V=%g f=%g R=%g C=%g" % (ir.component("V1").value,
                               ir.component("V1").params[5],
                               ir.component("R1").value, ir.component("C1").value))

ir, rep = ok("正弦源 V1 = 1V，频率 1kHz；电阻 R1 = 1kΩ；电容 C1 = 159nF；"
             "串联后到地；在 R1 两端各放一个电压探针。")
check("显式位号被沿用", [c.refdes for c in ir.components] == ["V1", "R1", "C1", "GND1"],
      str([c.refdes for c in ir.components]))
check("'R1 两端' → 探针在 in 和 out", [p.net for p in ir.probes] == ["in", "out"],
      str([p.net for p in ir.probes]))

print("\n[正向] 数值量级与仿真参数")
ir, rep = ok("100mV、2kHz 正弦信号源，经过 2.2kΩ 电阻接 100nF 电容到地，"
             "在输入和输出各放一个探针，仿真 6ms，采样率 200kHz。")
check("100mV → 0.1 V", abs(ir.component("V1").value - 0.1) < 1e-12,
      "%g" % ir.component("V1").value)
check("2.2kΩ → 2200 Ω", abs(ir.component("R1").value - 2200.0) < 1e-9,
      "%g" % ir.component("R1").value)
check("100nF → 1e-7 F", abs(ir.component("C1").value - 1e-7) < 1e-18,
      "%g" % ir.component("C1").value)
check("仿真 6ms", abs(ir.simulation.stop - 0.006) < 1e-12, "%g" % ir.simulation.stop)
check("采样率 200kHz", abs(ir.simulation.sample_rate - 200000.0) < 1e-9,
      "%g" % ir.simulation.sample_rate)

ir, rep = ok("1V 1kHz 正弦源，经过 1kΩ 电阻接 159nF 电容到地，"
             "在输出放探针，仿真 3 个周期。")
check("'3 个周期' → 3 ms", abs(ir.simulation.stop - 0.003) < 1e-12,
      "%g" % ir.simulation.stop)

ir, rep = ok("1V 1kHz 正弦源，经过 1kΩ 电阻接 159nF 电容到地，在输出放探针，仿真 10ms。")
check("'仿真 10ms' → 0.01 s", abs(ir.simulation.stop - 0.01) < 1e-12,
      "%g" % ir.simulation.stop)

print("\n[正向] 只有一个无源元件时'两端'探针")
ir, rep = ok("1V 1kHz 正弦源，经过 1kΩ 电阻到地，在电阻两端放电压探针。")
check("网络只有 in / 0", [n.name for n in ir.nets] == ["in", "0"],
      str([n.name for n in ir.nets]))
check("探针在 in 和 0", [p.net for p in ir.probes] == ["in", "0"],
      str([p.net for p in ir.probes]))

# ---------------------------------------------------------------- 反向
print("\n[反向] 缺信息 / 不支持的拓扑与元件，必须报错并说清原因")
bad("", "描述为空")
bad("帮我画个电路", "没识别出任何元件")
bad("1V 1kHz 正弦源，经过 1kΩ 电阻接 159nF 电容，在输出放探针。", "没找到地")
bad("经过 1kΩ 电阻接 159nF 电容到地，在输出放探针。", "没找到信号源")
bad("1V 1kHz 正弦源和 1kΩ 电阻并联，到地，在输出放探针。", "只支持")
bad("1V 1kHz 正弦源，经过 10mH 电感到地，在输出放探针。", "不在已验证白名单")
bad("1V 1kHz 正弦源，经过一个运放到地，在输出放探针。", "不在已验证白名单")
bad("创建一个 5V 直流电源串联 1kΩ 电阻接地的电路，在电阻两端放电压探针。", "直流源")
bad("1V 正弦源，经过 1kΩ 电阻接 159nF 电容到地，在输出放探针。", "没给频率")
bad("1V 1kHz 正弦源，经过 1kΩ 电阻接电容到地，在输出放探针。", "没给容值")
bad("1V 1kHz 正弦源，经过电阻接 159nF 电容到地，在输出放探针。", "没给阻值")
bad("把 R1 改成 2kΩ。", "只支持从零新建")
bad("1V 1kHz 正弦源，经过 1kΩ 电阻接 159nF 电容到地，做交流分析。", "只支持瞬态")
bad("1V 1kHz 正弦源，经过 1kΩ 电阻接 159nF 电容到地，做直流工作点分析。", "只支持瞬态")
bad("1V 1kHz 正弦源，经过 1kΩ 电阻接 159nF 电容到地，在探针放一个电压探针。", "看不懂探针位置")
bad("1V 1kHz 正弦源，经过 1kΩ 电阻、1kΩ 电阻、159nF 电容到地，在输出放探针。",
    "超过已验证上限")
bad("1V 1kHz 正弦源和 2V 2kHz 正弦源，经过 1kΩ 电阻到地，在输出放探针。", "多个电源")

print("\n[反向] 报错时不得产生任何文件")
import tempfile
tmp = os.path.join(tempfile.gettempdir(), "nl2ir_should_not_exist.ir.json")
if os.path.exists(tmp):
    os.remove(tmp)
try:
    nl2ir.parse("1V 1kHz 正弦源，经过 1kΩ 电阻并联到地。")
except nl2ir.NLParseError:
    pass
check("解析器本身不写文件", not os.path.exists(tmp))

print("\n" + "-" * 80)
print("总计 %d 项通过，%d 项失败 => %s" % (npass, fails, "PASS" if not fails else "FAIL"))
print("-" * 80)
sys.exit(0 if not fails else 1)
