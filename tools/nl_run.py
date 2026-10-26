# -*- coding: utf-8 -*-
"""一句中文 -> 电路 -> 仿真 -> 数字对得上理论（端到端验收）。

链路：
    中文描述
      -> nl2ir.parse()      Circuit IR（纯 JSON，无 Multisim 概念）
      -> CircuitIR.validate()
      -> ir_compile          .ms14
      -> Multisim 瞬态
      -> COM 读探针
      -> fitlib 最小二乘拟合
      -> 与理论值比对

判定用的是 **IR 里写的元件值** 算出来的理论值，不是 Multisim 报回来的值 ——
否则就成了"自己和自己比"。Multisim 报回的 R/C 值只作为旁证打印。

必须 32 位 Python（COM 限制）：
    runtime\\py32\\python.exe tools/nl_run.py "1V 1kHz 正弦源，经过 1kΩ 电阻后接 ..."
    runtime\\py32\\python.exe tools/nl_run.py --file examples/nl/rc_lowpass.txt

退出码：0 全部通过 / 2 解析失败 / 3 判定失败 / 4 前置条件不满足
"""
import argparse
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import ir_compile           # noqa: E402
import ir_sim               # noqa: E402
import nl2ir                # noqa: E402

OUT_DIR = os.path.join(ROOT, "out", "nl")
BASELINE = os.path.join(ROOT, "out", "p19_rc_main.json")     # 直接 add_part 的实测基线
fails = []


def check(name, cond, detail=""):
    print("  %-46s %s%s" % (name, "OK" if cond else "FAIL",
                            ("  " + detail) if detail else ""))
    if not cond:
        fails.append(name)


def main(argv=None):
    ap = argparse.ArgumentParser(description="中文 -> IR -> .ms14 -> 仿真 -> 判定")
    ap.add_argument("text", nargs="?", help="电路描述")
    ap.add_argument("--file", help="从文本文件读描述")
    ap.add_argument("--out", help="输出 .ms14 路径（默认 out/nl/<name>.ms14）")
    ap.add_argument("--sim-only", action="store_true", help="只跑仿真，不做理论判定")
    args = ap.parse_args(argv)

    text = args.text
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    if not text:
        ap.error("要么给一句话，要么用 --file")

    print("=" * 78)
    print("自然语言 -> 电路 -> 仿真 端到端验收")
    print("=" * 78)
    print("[输入] %s" % text.strip())

    # ---------- 1) 解析 ----------
    print()
    print("[1] 中文 -> Circuit IR")
    try:
        ir, rep = nl2ir.parse(text)
    except nl2ir.NLParseError as e:
        print("  解析失败，未生成任何文件：")
        for it in e.issues:
            print("    - %s" % it)
        return 2
    print("  我理解成：%s" % rep["explain"])
    for n in rep["notes"]:
        print("  · %s" % n)
    for w in rep["warnings"]:
        print("  ! %s" % w)

    errs = ir.validate()
    check("IR 通过 validate()", not errs, str(errs) if errs else "")
    if errs:
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    ir_path = os.path.join(OUT_DIR, "%s.ir.json" % ir.name)
    ir.save(ir_path)
    print("  IR -> %s" % os.path.relpath(ir_path, ROOT))

    # ---------- 2) 编译 ----------
    print()
    print("[2] IR -> .ms14")
    ms14 = args.out or os.path.join(OUT_DIR, "%s.ms14" % ir.name)
    try:
        crep = ir_compile.compile_ir(ir, ms14, verbose=True)
    except ir_compile.CompileError as e:
        print("  编译失败：%s" % e)
        return 2
    check(".ms14 已生成", os.path.exists(ms14), "%d 字节" % crep["bytes"])
    check("探针数量与 IR 一致", len(crep["probes"]) == len(ir.probes),
          "%d / %d" % (len(crep["probes"]), len(ir.probes)))

    # ---------- 3) 仿真 ----------
    print()
    print("[3] Multisim 瞬态")
    sim = ir.simulation
    res = ir_sim.simulate(ms14, sim.stop, sim.sample_rate)
    check("Multisim 打开并注册探针", len(res["outputs"]) == len(ir.probes),
          "%d 个输出 %s" % (len(res["outputs"]), res["outputs"]))
    check("每个探针都读到波形", len(res["data"]) == len(ir.probes),
          "读到 %d 个通道" % len(res["data"]))
    if len(res["data"]) < len(ir.probes):
        return 4

    # ---------- 4) 拟合 ----------
    print()
    print("[4] 最小二乘拟合（跳过前 40% 采样，避开起始暂态）")
    try:
        m = ir_sim.measure(ir, res)
    except RuntimeError as e:
        print("  %s" % e)
        return 4
    for nm, ch in m["channels"].items():
        print("  %-14s A=%.5f  φ=%.2f°  偏置=%.5f"
              % (nm, ch["amp"], ch["phase_deg"], ch["offset"]))
    print("  模式：%s（%s）"
          % (m["mode"], "输出/输入" if m["mode"] == "ratio"
             else "只有一个探针，用声明幅值 %.3g V 当参考" % m["source_amp"]))

    th = ir_sim.theory(ir)
    if th:
        print("  理论：f=%.0f Hz  R=%.4g Ω  C=%.4g F  fc=%.1f Hz"
              % (th["freq"], th["r"], th["c"], th["fc"]))
        print("        |H|=%.5f  ∠H=%.2f°" % (th["gain"], th["phase_deg"]))
    else:
        print("  理论：这个拓扑没有内置解析解，只报告实测值")

    # ---------- 5) 判定 ----------
    print()
    print("[5] 判定")
    if m["mode"] == "ratio":
        check("输入幅值 ≈ 声明 %.3g V" % m["source_amp"],
              abs(m["channels"][m["in_name"]]["amp"] - m["source_amp"])
              <= 0.02 * m["source_amp"],
              "实测 %.5f" % m["channels"][m["in_name"]]["amp"])
    if th and not args.sim_only:
        check("增益 ≈ 理论 |H|=%.5f" % th["gain"], abs(m["gain"] - th["gain"]) <= 0.02,
              "实测 %.5f（误差 %.5f）" % (m["gain"], abs(m["gain"] - th["gain"])))
        check("相位 ≈ 理论 ∠H=%.2f°" % th["phase_deg"],
              abs(m["phase_deg"] - th["phase_deg"]) <= 3.0,
              "实测 %.2f°（误差 %.2f°）" % (m["phase_deg"],
                                          abs(m["phase_deg"] - th["phase_deg"])))

    # 与 v0.3.0 手工 IR / 直接 add_part 的实测基线对比：只在同一电路上比
    base = None
    if os.path.exists(BASELINE):
        try:
            b = json.load(open(BASELINE, encoding="utf-8"))
            if th and abs(th["freq"] - 1000.0) < 1e-6 and abs(th["r"] - 1000.0) < 1e-6 \
                    and abs(th["c"] - 159e-9) < 1e-15:
                base = b
        except Exception as e:
            print("  基线读取失败：%s" % e)
    if base:
        dg = abs(m["gain"] - base["gain"])
        dp = abs(m["phase_deg"] - base["phase_deg"])
        check("增益与直接 add_part 基线一致（Δ<=1e-4）", dg <= 1e-4,
              "基线 %.5f  NL %.5f  Δ=%.2e" % (base["gain"], m["gain"], dg))
        check("相位与直接 add_part 基线一致（Δ<=0.05°）", dp <= 0.05,
              "基线 %.2f°  NL %.2f°  Δ=%.3f°" % (base["phase_deg"],
                                                 m["phase_deg"], dp))

    # ---------- 6) 落盘 ----------
    names = list(res["data"])
    npts = min(len(v) for _t, v in res["data"].values())
    csv_path = os.path.join(OUT_DIR, "%s.waveform.csv" % ir.name)
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("t," + ",".join(names) + "\n")
        for i in range(npts):
            f.write("%.9g" % res["data"][names[0]][0][i])
            for nm in names:
                f.write(",%.9g" % res["data"][nm][1][i])
            f.write("\n")

    out = {
        "text": text.strip(),
        "ir": os.path.relpath(ir_path, ROOT),
        "ms14": os.path.relpath(ms14, ROOT),
        "understood": rep["explain"],
        "outputs": res["outputs"],
        "state": res["state"],
        "rlc_reported_by_multisim": res["rlc"],
        "channels": m["channels"],
        "mode": m["mode"],
        "gain": m["gain"],
        "phase_deg": m["phase_deg"],
        "theory": th,
        "pass": not fails,
        "fails": list(fails),
        "csv": os.path.relpath(csv_path, ROOT),
    }
    jpath = os.path.join(OUT_DIR, "%s.result.json" % ir.name)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
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
    os._exit(code)      # COM 句柄不释放也没关系，进程直接退，避免卡住
