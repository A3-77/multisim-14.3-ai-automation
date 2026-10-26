# -*- coding: utf-8 -*-
"""Circuit IR 自检：JSON 往返必须无损，摘要必须可读。

不依赖 Multisim，可以随时跑。

用法：
    python tools/test_ir.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as ir  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "rc_lowpass.ir.json")
fails = 0


def check(name, cond, detail=""):
    global fails
    print("  %-46s %s%s" % (name, "OK" if cond else "FAIL",
                            ("  " + detail) if detail else ""))
    if not cond:
        fails += 1


print("=" * 70)
print("Circuit IR 自检")
print("=" * 70)

print("[1] 加载示例")
c = ir.CircuitIR.load(EXAMPLE)
print(c.summary())
print()

print("[2] 结构")
check("元件数 = 4", len(c.components) == 4, "got %d" % len(c.components))
check("网络数 = 3", len(c.nets) == 3, "got %d" % len(c.nets))
check("探针数 = 2", len(c.probes) == 2, "got %d" % len(c.probes))
check("analysis = transient", c.simulation.analysis == "transient")
check("stop = 6ms", abs(c.simulation.stop - 0.006) < 1e-12)

print()
print("[3] params 键类型（JSON 读回来必须是 int）")
p = c.component("V1").params
check("V1.params 是 dict", isinstance(p, dict))
check("V1.params 键是 int", all(isinstance(k, int) for k in p), str(p))
check("V1 频率参数 = 1000", p.get(5) == 1000.0, str(p.get(5)))

print()
print("[4] 网络解析")
n = c.net("0")
check("net 0 有 3 个引脚", len(n.pins) == 3, str(n.pins))
check("net 0 引用 V1.-", ("V1", "-") in n.refs(), str(n.refs()))

print()
print("[5] JSON 往返无损")
d1 = c.to_dict()
tmp = os.path.join(tempfile.gettempdir(), "ir_roundtrip.json")
c.save(tmp)
c2 = ir.CircuitIR.load(tmp)
d2 = c2.to_dict()
check("往返后 to_dict 完全一致", d1 == d2)
check("往返后 params 键仍是 int",
      all(isinstance(k, int) for k in c2.component("V1").params))
os.remove(tmp)

print()
print("[6] 不暴露底层实现细节")
raw = open(EXAMPLE, encoding="utf-8").read()
banned = ["CiID", "CiPort", "CIITSymbolComp", "Transformer-M20", "CiaParamList",
          "CODPinComp", "CiNode", "&ASC", "&UNI"]
hits = [b for b in banned if b in raw]
check("IR 文件里没有任何 XML 概念", not hits, str(hits))

print()
print("-" * 70)
print("总计：%s" % ("全部通过" if fails == 0 else "%d 项失败" % fails))
sys.exit(0 if fails == 0 else 1)
