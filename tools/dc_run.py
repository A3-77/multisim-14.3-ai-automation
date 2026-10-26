# -*- coding: utf-8 -*-
"""DC 静态电路验收：5V 直流源 → 1kΩ → 地，读电阻两端电压与电流。

实测结论（先看这个再改代码）
--------------------------
静态电路**用 transient 就能取数**，不需要 DC 工作点。之前的"DC 取不到数"
是实验脚本自己造成的：

    run() 之后、read() 之前**再调用一次 EnumOutputs()**，
    会让随后的 GetOutputData() 全部返回 E_FAIL（-2147467259 未指定的错误）。

证据在 out/dc/bisect_P4.json（对照组 P0~P3 都正常）。所以本脚本的铁律是：

    打开电路时枚举一次输出 → 之后全程用缓存的名字，
    直到读完数据都不再碰 EnumOutputs / 不再重复 probes()。

两种模式
--------
    --mode transient（默认）  RunSimulation + SetOutputRequest，与 AC 链路完全一致
    --mode dcop                DoDCOperatingPoint，验证"静态分析"这条路是否也通

必须 32 位 Python：
    runtime\\py32\\python.exe -u tools/dc_run.py
    runtime\\py32\\python.exe -u tools/dc_run.py --mode dcop
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import msc  # noqa: E402

OUT_DIR = os.path.join(ROOT, "out", "dc")
MS14 = os.path.join(OUT_DIR, "dc_min.ms14")
fails = []


def check(name, cond, detail=""):
    print("  %-44s %s%s" % (name, "OK" if cond else "FAIL",
                            ("  " + detail) if detail else ""))
    if not cond:
        fails.append(name)


def read_probe(circ, name):
    """只读，不做任何枚举。失败直接抛，让调用方看见原文。"""
    t, v = circ.read(name)
    return list(t), list(v)


def main():
    ap = argparse.ArgumentParser(description="DC 静态电路验收")
    ap.add_argument("--ms14", default=MS14)
    ap.add_argument("--mode", choices=["transient", "dcop"], default="transient")
    ap.add_argument("--volt", type=float, default=5.0, help="期望的源电压（仅用于判定）")
    ap.add_argument("--ohm", type=float, default=1000.0, help="期望的电阻（仅用于判定）")
    args = ap.parse_args()

    print("=" * 78)
    print("DC 静态电路验收（%s）" % args.mode)
    print("=" * 78)
    print("[电路] %s" % os.path.relpath(args.ms14, ROOT))

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)

    ms = msc.Multisim()
    circ = ms.open(args.ms14)

    # ---- 只在这里枚举一次 ----
    outs = list(circ.probes())
    print("[探针] %s" % outs)
    check("打开后探针已注册", len(outs) >= 2, "%d 个" % len(outs))
    if len(outs) < 2:
        sys.stdout.flush()
        os._exit(4)

    stop, sr, n = 0.006, 200000.0, 1200
    if args.mode == "transient":
        for nm in outs:
            circ.request_output(nm, sr, n, method=msc.Interp.Linear)
        circ.run(stop, pause=False)
        deadline = time.time() + 15.0
        got = ()
        while time.time() < deadline:
            got, _to = circ.wait(500)
            if got:
                break
            if circ.state == msc.SimState.Stopped:
                break
        print("[仿真] state=%s got=%s" % (circ.state, got))
        time.sleep(0.5)
    else:
        for nm in outs:
            circ.request_output(nm, sr, n, method=msc.Interp.Linear)
        try:
            circ._c.DoDCOperatingPoint(msc._bstr_array(outs))
            print("[仿真] DoDCOperatingPoint 调用成功")
        except Exception as e:
            print("[仿真] DoDCOperatingPoint 失败：%s" % e)
        time.sleep(1.0)

    # ---- 读数：中间绝不调用 EnumOutputs ----
    data = {}
    for nm in outs:
        try:
            t, v = read_probe(circ, nm)
            data[nm] = (t, v)
            print("  %-12s n=%-5d min=%-10.6g max=%-10.6g"
                  % (nm, len(v), min(v), max(v)))
        except Exception as e:
            print("  %-12s 读取失败: %s" % (nm, e))

    # RLCValue 放在读完之后（P3 证明读之前调也无害，但没必要冒险）
    r_val = None
    try:
        r_val = circ.rlc("R1")
    except Exception as e:
        print("  RLCValue(R1) 失败: %s" % e)
    try:
        circ.stop()
    except Exception:
        pass

    check("两个探针都读到数据", len(data) == len(outs), "%d / %d" % (len(data), len(outs)))
    if len(data) < 2:
        sys.stdout.flush()
        os._exit(5)

    # ---- 判定 ----
    names = list(data)
    v_in = sum(data[names[0]][1]) / len(data[names[0]][1])
    v_gnd = sum(data[names[1]][1]) / len(data[names[1]][1])
    v_r = v_in - v_gnd
    r_used = r_val if r_val else args.ohm
    i_r = v_r / r_used

    print()
    print("[读数] V(in)=%.6f V   V(0)=%.6f V   V_R=%.6f V   R=%.3f Ω   I=%.6f A"
          % (v_in, v_gnd, v_r, r_used, i_r))
    print("[来源] 电压 = Multisim 探针实测；R = Multisim RLCValue；I = V_R / R（按欧姆定律算）")
    print()
    check("V(in) ≈ %g V" % args.volt, abs(v_in - args.volt) <= 0.02 * args.volt,
          "实测 %.6f" % v_in)
    check("V(0) ≈ 0 V", abs(v_gnd) <= 1e-3, "实测 %.6f" % v_gnd)
    check("电阻两端电压 ≈ %g V" % args.volt, abs(v_r - args.volt) <= 0.02 * args.volt,
          "实测 %.6f" % v_r)
    check("电流 ≈ %g mA" % (args.volt / r_used * 1000),
          abs(i_r - args.volt / r_used) <= 0.02 * (args.volt / r_used),
          "实测 %.6f A" % i_r)
    check("R1 由 Multisim 报回 %g Ω" % args.ohm,
          r_val is not None and abs(r_val - args.ohm) < 1e-6, "实测 %s" % r_val)

    # ---- 落盘 ----
    tag = "transient" if args.mode == "transient" else "dcop"
    csv_path = os.path.join(OUT_DIR, "dc_%s_waveform.csv" % tag)
    npts = min(len(v) for _t, v in data.values())
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("t," + ",".join(names) + "\n")
        for i in range(npts):
            f.write("%.9g" % data[names[0]][0][i])
            for nm in names:
                f.write(",%.9g" % data[nm][1][i])
            f.write("\n")

    res = {
        "ms14": os.path.relpath(args.ms14, ROOT),
        "mode": args.mode,
        "outputs": outs,
        "v_in": v_in, "v_gnd": v_gnd, "v_resistor": v_r,
        "r_reported_by_multisim": r_val, "current": i_r,
        "current_source": "I = V_R / R（R 来自 Multisim RLCValue）",
        "pass": not fails, "fails": list(fails),
        "csv": os.path.relpath(csv_path, ROOT),
    }
    jpath = os.path.join(OUT_DIR, "dc_result_%s.json" % tag)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print()
    print("波形 %s（%d 行）" % (os.path.relpath(csv_path, ROOT), npts))
    print("结果 %s" % os.path.relpath(jpath, ROOT))
    print()
    print("=" * 78)
    print("结论：%s" % ("全部通过" if not fails else "失败项 %s" % fails))
    print("=" * 78)
    sys.stdout.flush()
    return 0 if not fails else 3


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
