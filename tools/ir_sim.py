# -*- coding: utf-8 -*-
"""IR 的仿真内核：打开 .ms14 -> 跑瞬态 -> 读探针 -> 最小二乘拟合。

为什么单独抽一个文件
--------------------
`tools/ir_run.py` 是 v0.3.0 的验收脚本，它的判定里写死了"和 p19 基线对比"，
属于**某一次验收的结论**，不适合被别的入口复用。这里只抽"跑仿真 + 拟合"这段
纯执行逻辑，供 nl_run.py 使用；ir_run.py 保持原样不动。

取数顺序的关键点（都是踩过的坑，别改）
--------------------------------------
1. `request_output` 必须在 `run()` **之前**注册，否则 `EnumOutputs` 里没有数据源。
2. 读数必须在 `stop()` **之前**，停掉之后 buffer 就没了。
3. `EnumOutputs()` 的顺序 = 探针在文件里的序号（编译时 add_probe_ext(index=i)），
   所以 IR 里第 k 个探针 == outs[k]。
4. 仿真窗口太短（比如只有半个周期）时拟合会拿到半截正弦，结果不可信 ——
   nl2ir 默认给 6 个周期，就是为了避开这个。
"""
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)        # msc.py 在仓库根目录

import fitlib  # noqa: E402
import msc     # noqa: E402


def kill_multisim():
    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)


def simulate(ms14_path, stop, sample_rate, timeout=40.0, verbose=True):
    """打开 ms14、跑瞬态、读所有探针。返回 dict。"""
    stop = float(stop)
    sample_rate = float(sample_rate)
    npts = int(min(max(200, stop * sample_rate), 20000))

    kill_multisim()
    ms = msc.Multisim()
    circ = ms.open(ms14_path)
    outs = list(circ.probes())
    if verbose:
        print("  outputs: %s" % outs)

    for nm in outs:
        try:
            circ.request_output(nm, sample_rate, npts, method=msc.Interp.Linear)
        except Exception as e:
            print("  request_output(%s) 失败: %s" % (nm, e))

    circ.run(stop, pause=False)
    deadline = time.time() + timeout
    got = ()
    while time.time() < deadline:
        try:
            got, _to = circ.wait(500)
        except Exception as e:
            print("  wait 失败: %s" % e)
            break
        if got:
            break
        if circ.state == msc.SimState.Stopped:
            break

    data = {}
    for nm in outs:
        try:
            t, v = circ.read(nm)
        except Exception as e:
            print("  read(%s) 失败: %s" % (nm, e))
            continue
        if v:
            data[nm] = (list(t), list(v))
            if verbose:
                print("  %-14s n=%d  t=[%.6g, %.6g]" % (nm, len(v), t[0], t[-1]))

    rlc = {}
    for ref in _rlc_refs(circ):
        try:
            rlc[ref] = circ.rlc(ref)
        except Exception:
            rlc[ref] = None

    state = str(circ.state)
    try:
        circ.stop()
    except Exception:
        pass
    return {"outputs": outs, "data": data, "rlc": rlc, "state": state,
            "n": npts, "stop": stop, "sample_rate": sample_rate}


def _rlc_refs(circ):
    """尽力列出 R/C 位号（读不到就算了，不影响主流程）。"""
    refs = []
    try:
        for c in circ.components():
            rd = str(c)
            if rd[:1] in ("R", "C", "L"):
                refs.append(rd)
    except Exception:
        pass
    return refs[:8]


def fit_channels(data, freq, skip=0.4):
    """对每个通道做已知频率的正弦最小二乘拟合，返回 [(name, amp, phase_rad, offset)]。

    跳过前 skip 比例的点：那一段还在起始暂态里，不是稳态。
    """
    out = []
    for nm, (t, v) in data.items():
        k0 = int(len(t) * skip)
        fit = fitlib.fit_sine(t[k0:], v[k0:], freq)
        if fit is None:
            continue
        amp, ph, off = fit
        out.append((nm, amp, ph, off))
    return out


def measure(ir, sim_result):
    """把仿真结果折成"增益 / 相位"两个数。

    返回 dict：gain / phase_deg / source_amp / source_freq / channels / mode
    mode = "ratio"（两个探针，输出/输入）或 "absolute"（只有一个探针，用声明的幅值当参考）
    """
    src = next((c for c in ir.components
                if c.family == "SIGNAL_VOLTAGE_SOURCES"), None)
    if src is None:
        raise RuntimeError("IR 里没有信号源")
    freq = float((src.params or {}).get(5) or 0.0)
    amp = float(src.value or 0.0)

    fits = fit_channels(sim_result["data"], freq)
    if not fits:
        raise RuntimeError("没有任何通道拟合成功（探针没注册上，或仿真没跑起来）")

    chans = {}
    for nm, a, ph, off in fits:
        chans[nm] = {"amp": a, "phase_deg": math.degrees(ph), "offset": off}

    # IR 里的探针顺序 = 编译序号 = EnumOutputs 顺序
    if len(fits) >= 2:
        (n1, a1, p1, _o1), (n2, a2, p2, _o2) = fits[0], fits[1]
        gain = a2 / a1
        dph = math.degrees(p2 - p1)
        mode = "ratio"
    else:
        n1, a1, p1, _o = fits[0]
        n2 = None
        gain = a1 / amp if amp else float("nan")
        dph = math.degrees(p1)
        mode = "absolute"
    while dph > 180:
        dph -= 360
    while dph < -180:
        dph += 360

    return {"gain": gain, "phase_deg": dph, "mode": mode,
            "source_amp": amp, "source_freq": freq,
            "channels": chans, "in_name": n1, "out_name": n2}


def simulate_dc(ms14_path, sample_rate=200000.0, npts=1200, verbose=True):
    """直流工作点：DoDCOperatingPoint -> 读探针（每个探针 1 个点）。

    **铁律**：读之前不要再调 EnumOutputs（probes()）。
    实测在 run/分析之后、read 之前多枚举一次输出，会让 GetOutputData 全部
    返回 E_FAIL（证据 out/dc/bisect_P4.json，对照组 P0~P3 均正常）。
    """
    kill_multisim()
    ms = msc.Multisim()
    circ = ms.open(ms14_path)
    outs = list(circ.probes())          # 只在这里枚举一次
    if verbose:
        print("  outputs: %s" % outs)

    for nm in outs:
        try:
            circ.request_output(nm, sample_rate, npts, method=msc.Interp.Linear)
        except Exception as e:
            print("  request_output(%s) 失败: %s" % (nm, e))

    err = None
    try:
        circ._c.DoDCOperatingPoint(msc._bstr_array(outs))
    except Exception as e:
        err = str(e)
        print("  DoDCOperatingPoint 失败: %s" % e)
    time.sleep(1.0)

    data = {}
    for nm in outs:
        try:
            t, v = circ.read(nm)
        except Exception as e:
            print("  read(%s) 失败: %s" % (nm, e))
            continue
        if v:
            data[nm] = (list(t), list(v))
            if verbose:
                print("  %-14s n=%d  min=%.6g  max=%.6g"
                      % (nm, len(v), min(v), max(v)))

    rlc = {}
    for ref in _rlc_refs(circ):
        try:
            rlc[ref] = circ.rlc(ref)
        except Exception:
            rlc[ref] = None
    state = str(circ.state)
    try:
        circ.stop()
    except Exception:
        pass
    return {"outputs": outs, "data": data, "rlc": rlc, "state": state,
            "n": npts, "stop": 0.0, "sample_rate": sample_rate, "dc_error": err}


def measure_dc(ir, sim_result):
    """直流电路的读数：把探针按 IR 里的网络名对齐，算电压差和电流。

    电压 = Multisim 探针实测；R = Multisim RLCValue；I = V_R / R（欧姆定律，明确标注来源）。
    """
    src = next((c for c in ir.components
                if c.family in ("POWER_SOURCES", "SIGNAL_VOLTAGE_SOURCES")
                and c.part != "GROUND"), None)
    if src is None:
        raise RuntimeError("IR 里没有电源")
    outs = sim_result["outputs"]
    data = sim_result["data"]
    if len(outs) != len(ir.probes):
        raise RuntimeError("探针数量对不上：电路里 %d 个，IR 里 %d 个"
                           % (len(outs), len(ir.probes)))
    if not data:
        raise RuntimeError("一个探针都没读到数据")

    by_net = {}
    for probe, nm in zip(ir.probes, outs):
        if nm in data:
            v = data[nm][1]
            by_net[probe.net] = {"output": nm, "mean": sum(v) / len(v),
                                 "min": min(v), "max": max(v), "n": len(v)}

    r = next((c for c in ir.components if c.family == "RESISTOR"), None)
    r_ms = None
    if r is not None:
        r_ms = sim_result.get("rlc", {}).get(r.refdes)

    v_in = by_net.get("in", {}).get("mean")
    v_gnd = by_net.get("0", {}).get("mean")
    v_r = None if (v_in is None or v_gnd is None) else v_in - v_gnd
    i_r = None
    if v_r is not None and (r_ms or (r and r.value)):
        i_r = v_r / (r_ms if r_ms else r.value)

    return {"mode": "dc", "channels": by_net,
            "v_in": v_in, "v_gnd": v_gnd, "v_resistor": v_r,
            "r_reported_by_multisim": r_ms, "current": i_r,
            "source_amp": float(src.value or 0.0),
            "source_refdes": src.refdes}


def theory_dc(ir):
    """直流串联链的理论值：只有 1 个电阻时才给"电阻电压 = 源电压、I = V/R"。"""
    src = next((c for c in ir.components
                if c.family in ("POWER_SOURCES", "SIGNAL_VOLTAGE_SOURCES")
                and c.part != "GROUND"), None)
    rs = [c for c in ir.components if c.family == "RESISTOR"]
    if src is None or len(rs) != 1:
        return None
    v = float(src.value or 0.0)
    return {"kind": "dc_series_r", "v": v, "r": rs[0].value,
            "v_resistor": v, "current": v / rs[0].value if rs[0].value else None}


def theory(ir):
    """按 IR 里写的元件值算理论值（不是用 Multisim 报回来的值）。

    目前只覆盖一阶 RC 低通（1 个 R + 1 个 C）。其它组合返回 None ——
    没有理论模型就不做数值判定，避免"自己和自己比"。
    """
    rs = [c for c in ir.components if c.family == "RESISTOR"]
    cs = [c for c in ir.components if c.family == "CAPACITOR"]
    src = next((c for c in ir.components
                if c.family == "SIGNAL_VOLTAGE_SOURCES"), None)
    if len(rs) != 1 or len(cs) != 1 or src is None:
        return None
    f = float((src.params or {}).get(5) or 0.0)
    if not f:
        return None
    g, ph, x = fitlib.lowpass_theory(f, rs[0].value, cs[0].value)
    return {"kind": "rc_lowpass", "gain": g, "phase_deg": math.degrees(ph),
            "fc": fitlib.cutoff(rs[0].value, cs[0].value),
            "r": rs[0].value, "c": cs[0].value, "freq": f}
