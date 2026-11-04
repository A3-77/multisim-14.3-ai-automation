# -*- coding: utf-8 -*-
"""扫描电位器参数下标：哪一个才是"百分比"。

判据：把候选下标设成 100%，若 Vb 掉到 0.5 V 左右、Vc 升到 12 V（截止），
说明这一档真的把电位器调到了 200 kΩ。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile          # noqa: E402
import hw_lab1             # noqa: E402

OUT = hw_lab1.OUT


def one(idx, pct):
    hw_lab1.POT_IDX = idx
    ir = hw_lab1.build(pct, "scan%d" % idx)
    ir.simulation.stop = 0.05
    ms14 = os.path.join(OUT, "scan_%d.ms14" % idx)
    ir_compile.compile_ir(ir, ms14, verbose=False)
    import ir_sim
    res = ir_sim.simulate(ms14, stop=0.05, sample_rate=200000.0,
                          timeout=120.0, verbose=False)
    d = res.get("data") or {}
    names = res.get("outputs") or []
    out = {}
    for i, nm in enumerate(names):
        tt, vv = d.get(nm, ([], []))
        if vv:
            k = max(1, int(len(vv) * 0.2))
            out[i + 1] = round(sum(vv[-k:]) / k, 4)
    return out


if __name__ == "__main__":
    res = {}
    for idx in range(8):
        try:
            r = one(idx, 100.0)
            res[idx] = r
            print("idx=%d  P1(vi)=%s P2(vb)=%s P3(vc)=%s P4(ve)=%s P5(vo)=%s"
                  % (idx, r.get(1), r.get(2), r.get(3), r.get(4), r.get(5)))
        except Exception as e:
            print("idx=%d 失败: %s" % (idx, e))
    with open(os.path.join(OUT, "pot_scan.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
