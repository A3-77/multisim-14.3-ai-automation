# -*- coding: utf-8 -*-
"""Circuit IR 校验的反向测试：每种错误都必须在写 .ms14 之前被拦住。

不需要 Multisim。

用法：
    python tools/test_ir_validate.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile           # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "rc_lowpass.ir.json")
BASE = json.load(open(EXAMPLE, encoding="utf-8"))
fails = 0


def check(name, cond, detail=""):
    global fails
    print("  %-50s %s%s" % (name, "OK" if cond else "FAIL",
                            ("  " + detail) if detail else ""))
    if not cond:
        fails += 1


def build(mutate=None):
    d = copy.deepcopy(BASE)
    if mutate:
        mutate(d)
    return irmod.CircuitIR.from_dict(d)


def expect(name, mutate, want):
    """构造一个坏 IR，要求错误列表里出现 want 这段文字。"""
    c = build(mutate)
    errs = c.validate()
    hit = [e for e in errs if want in e]
    check(name, bool(hit), hit[0] if hit else ("实际：%s" % (errs or "无错误")))


print("=" * 78)
print("Circuit IR 校验测试")
print("=" * 78)

print("\n[正向] 示例 IR 应当合法")
c = build()
errs = c.validate()
check("示例 IR 无错误", not errs, str(errs))
print("  警告：%s" % (c.warnings() or "无"))

print("\n[元件]")
expect("refdes 重复",
       lambda d: d["components"].append(dict(d["components"][1])),
       "refdes 重复")
expect("元件型号不在白名单",
       lambda d: d["components"][1].update({"part": "RESISTOR_RATED",
                                            "family": "RATED_VIRTUAL"}),
       "不在已验证白名单")
expect("position 长度不对",
       lambda d: d["components"][1].update({"position": [1.0, 2.0, 3.0]}),
       "position 必须是")
expect("position 不是数字",
       lambda d: d["components"][1].update({"position": ["a", "b"]}),
       "position 不是数字")

print("\n[网络]")
expect("引脚写法不对",
       lambda d: d["nets"][0].update({"pins": ["V1", "R1.1"]}),
       "引脚写法不对")
expect("引用不存在的元件",
       lambda d: d["nets"][0].update({"pins": ["V9.+", "R1.1"]}),
       "不存在的元件")
expect("引脚不存在",
       lambda d: d["nets"][0].update({"pins": ["V1.7", "R1.1"]}),
       "没有引脚")
expect("网络只有 1 个引脚",
       lambda d: d["nets"][0].update({"pins": ["R1.1"]}),
       "至少要 2 个")
expect("网络名重复",
       lambda d: d["nets"][1].update({"name": "in"}),
       "网络名重复")
expect("同一引脚接两条网络",
       lambda d: d["nets"].append({"name": "x", "pins": ["R1.1", "C1.1"]}),
       "已经属于网络")
expect("别名归一化后仍能查出重复（V1.+ 与 V1.1 是同一引脚）",
       lambda d: d["nets"].append({"name": "x", "pins": ["V1.1", "C1.1"]}),
       "已经属于网络")
expect("孤立元件",
       lambda d: d["components"].append(
           {"refdes": "R9", "family": "RESISTOR", "part": "RESISTOR_VIRTUAL",
            "value": 100.0}),
       "孤立元件")

print("\n[探针]")
expect("目标网络不存在",
       lambda d: d["probes"][0].update({"net": "nope"}),
       "目标网络")
expect("探针与元件重名",
       lambda d: d["probes"][0].update({"refdes": "R1"}),
       "与元件重名")
expect("探针 refdes 重复",
       lambda d: d["probes"][1].update({"refdes": "P1"}),
       "探针 refdes 重复")
expect("net 和 at 同时给",
       lambda d: d["probes"][0].update({"at": [1.0, 2.0]}),
       "只能给一个")
expect("net 和 at 都不给",
       lambda d: d["probes"][0].pop("net"),
       "必须给 net")
expect("kind 不是 V",
       lambda d: d["probes"][0].update({"kind": "I"}),
       "不支持")

print("\n[仿真]")
expect("analysis 不支持",
       lambda d: d["simulation"].update({"analysis": "ac"}),
       "不支持")
expect("stop = 0",
       lambda d: d["simulation"].update({"stop": 0}),
       "stop 必须大于 0")
expect("start >= stop",
       lambda d: d["simulation"].update({"start": 0.01}),
       "必须小于 stop")
expect("采样率 <= 0",
       lambda d: d["simulation"].update({"sample_rate": 0}),
       "sample_rate 必须大于 0")
expect("采样点太少",
       lambda d: d["simulation"].update({"sample_rate": 1.0}),
       "采样点太少")
expect("step 比窗口还大",
       lambda d: d["simulation"].update({"step": 1.0}),
       "比仿真窗口")

print("\n[落盘前拦截]")
bad = build(lambda d: d["components"][1].update({"part": "NOPE"}))
out = os.path.join(ROOT, "out", "_should_not_exist.ms14")
if os.path.exists(out):
    os.remove(out)
try:
    ir_compile.compile_ir(bad, out, verbose=False)
    check("非法 IR 必须抛 CompileError", False, "竟然编译成功了")
except ir_compile.CompileError as e:
    check("非法 IR 抛 CompileError", True)
    check("错误信息里有具体原因", "白名单" in str(e), str(e).splitlines()[0])
existed = os.path.exists(out)
check("非法 IR 没有写出任何 .ms14", not existed,
      "" if not existed else ("文件竟然存在：%s" % out))

print("\n[正向再确认] 合法 IR 仍然能编译")
good_out = os.path.join(ROOT, "out", "_validate_ok.ms14")
try:
    ir_compile.compile_ir(build(), good_out, verbose=False)
    check("合法 IR 编译成功", os.path.exists(good_out))
finally:
    if os.path.exists(good_out):
        os.remove(good_out)
    rep = os.path.splitext(good_out)[0] + ".compile.json"
    if os.path.exists(rep):
        os.remove(rep)

print()
print("-" * 78)
print("总计：%s" % ("全部通过" if fails == 0 else "%d 项失败" % fails))
sys.exit(0 if fails == 0 else 1)
