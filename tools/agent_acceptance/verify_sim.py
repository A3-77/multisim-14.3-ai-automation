# -*- coding: utf-8 -*-
"""独立复算 —— 不信 `measure`，从原始 CSV 自己算一遍。

为什么需要这个文件
------------------
`measure` 的 gain / phase 是 server 侧算的。如果它算错（或者更糟：根本没跑
仿真、数是编的），只看 `measure` 的返回是看不出来的。

所以这里做三件**互不依赖**的核对：

1. **文件层**：`.ms14` 真的存在？多大？CSV 有多少行？
2. **数据层**：从 CSV 重新做最小二乘拟合（本文件自己实现，不 import
   `fitlib` / `ir_sim`），得到 amp / phase；
3. **对账**：拟合值 vs `measure` 返回的 `channels[probe_id].amp / phase_deg`，
   差多少。

只要这三步都对得上，"measure 是编的"这条可能性就可以排除。

用法
----
    python tools/agent_acceptance/verify_sim.py \
        --trace out/agent_v08/p1/trace.jsonl --sim s-xxxxxxxxxx
"""
import argparse
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SESS_ROOT = os.path.join(ROOT, "out", "mcp", "sessions")


# ---------------------------------------------------------------------------
# 独立的最小二乘（y = a·sin + b·cos + c），不用任何项目代码
# ---------------------------------------------------------------------------
def fit_sine(t, v, f):
    w = 2.0 * math.pi * f
    n = len(t)
    if n < 8:
        return None
    # 用 3x3 正规方程 + 高斯消元；和项目里的实现是同一套数学，但代码是独立的
    s11 = s12 = s13 = s22 = s23 = s33 = 0.0
    r1 = r2 = r3 = 0.0
    for ti, vi in zip(t, v):
        st, ct = math.sin(w * ti), math.cos(w * ti)
        s11 += st * st
        s12 += st * ct
        s13 += st
        s22 += ct * ct
        s23 += ct
        s33 += 1.0
        r1 += st * vi
        r2 += ct * vi
        r3 += vi
    m = [[s11, s12, s13, r1],
         [s12, s22, s23, r2],
         [s13, s23, s33, r3]]
    for i in range(3):
        piv = max(range(i, 3), key=lambda k: abs(m[k][i]))
        if abs(m[piv][i]) < 1e-12:
            return None
        m[i], m[piv] = m[piv], m[i]
        pv = m[i][i]
        for j in range(i, 4):
            m[i][j] /= pv
        for k in range(3):
            if k != i and abs(m[k][i]) > 0:
                f2 = m[k][i]
                for j in range(i, 4):
                    m[k][j] -= f2 * m[i][j]
    a, b, c = m[0][3], m[1][3], m[2][3]
    return math.hypot(a, b), math.degrees(math.atan2(b, a)), c


# ---------------------------------------------------------------------------
def find_sim_record(sim_id):
    for cid in os.listdir(SESS_ROOT) if os.path.isdir(SESS_ROOT) else []:
        p = os.path.join(SESS_ROOT, cid, "sims", "%s.json" % sim_id)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return cid, json.load(f)
    return None, None


def read_trace(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def find_in_trace(recs, tool, sim_id):
    hit = None
    for r in recs:
        if r.get("tool") != tool:
            continue
        res = r.get("result") or {}
        if res.get("sim_id") == sim_id:
            hit = r
    return hit


def find_measure(recs, sim_id):
    """挑一条**字段齐全**的 measure 记录。

    同一个 sim 可能被 measure 过多次（`what=amplitude` / `what=phase` 会把
    另一组字段过滤掉），所以要优先选 channels 里同时有 amp 和 phase_deg 的那条，
    否则对账时 KeyError。
    """
    cands = [r for r in recs
             if r.get("tool") == "measure"
             and (r.get("result") or {}).get("sim_id") == sim_id]
    for r in reversed(cands):
        chans = (r.get("result") or {}).get("channels") or {}
        if chans and all("amp" in c and "phase_deg" in c for c in chans.values()):
            return r
    return cands[-1] if cands else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--sim", required=True)
    ap.add_argument("--skip", type=float, default=0.4,
                    help="跳过前多少比例的采样点（起始暂态），默认 0.4")
    ap.add_argument("--json", default=None, help="把结果同时写一份 JSON")
    o = ap.parse_args(argv)

    out = {"ok": False, "sim_id": o.sim, "checks": {}, "channels": {}}

    cid, rec = find_sim_record(o.sim)
    if rec is None:
        out["error"] = "找不到仿真记录 %s" % o.sim
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1
    out["circuit_id"] = cid

    # ---------- 1. 文件层 ----------
    ms14 = os.path.join(ROOT, rec.get("ms14") or "")
    csv_path = os.path.join(ROOT, rec.get("waveform") or "")
    rec_path = os.path.join(SESS_ROOT, cid, "sims", "%s.json" % o.sim)
    files = {
        "ms14": {"path": rec.get("ms14"),
                 "exists": os.path.isfile(ms14),
                 "bytes": os.path.getsize(ms14) if os.path.isfile(ms14) else None},
        "waveform_csv": {"path": rec.get("waveform"),
                         "exists": os.path.isfile(csv_path),
                         "bytes": (os.path.getsize(csv_path)
                                   if os.path.isfile(csv_path) else None)},
        "sim_record": {"path": os.path.relpath(rec_path, ROOT),
                       "exists": os.path.isfile(rec_path),
                       "bytes": (os.path.getsize(rec_path)
                                 if os.path.isfile(rec_path) else None)},
    }
    out["checks"]["files"] = files
    if not files["ms14"]["exists"] or not files["waveform_csv"]["exists"]:
        out["error"] = "产物缺失"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    # ---------- 2. 数据层：从 CSV 自己拟合 ----------
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0][1:]
    t = [float(r[0]) for r in rows[1:] if r]
    data = {nm: [] for nm in header}
    for r in rows[1:]:
        if not r:
            continue
        for i, nm in enumerate(header, 1):
            data[nm].append(float(r[i]))
    out["checks"]["csv"] = {"rows": len(rows) - 1, "columns": header,
                            "t_range": [t[0], t[-1]] if t else []}

    freq = float(rec.get("sample_rate") or 0.0)
    # 仿真记录里没存源频率，从 trace 的 simulate 参数推不出来 —— 用 measure
    # 返回里的 source_freq（那个值来自 IR，不受拟合影响）
    mrec = find_measure(read_trace(o.trace), o.sim)
    if mrec is None:
        out["error"] = "trace 里没有这个 sim 的 measure 调用，无法对账"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1
    meas = mrec["result"]
    src_f = float(meas.get("source_freq") or 0.0)
    if src_f <= 0:
        out["error"] = "measure 没给出 source_freq"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    k0 = int(len(t) * o.skip)
    fits = {}
    for nm in header:
        f = fit_sine(t[k0:], data[nm][k0:], src_f)
        if f:
            fits[nm] = {"amp": f[0], "phase_deg": f[1], "offset": f[2]}

    # ---------- 3. 对账：CSV 复算 vs measure ----------
    worst_amp = 0.0
    worst_ph = 0.0
    for pid, ch in (meas.get("channels") or {}).items():
        nm = ch.get("output")
        mine = fits.get(nm)
        if not mine:
            continue
        d_amp = abs(mine["amp"] - ch["amp"])
        r_amp = d_amp / ch["amp"] if ch["amp"] else None
        d_ph = abs(((mine["phase_deg"] - ch["phase_deg"] + 180) % 360) - 180)
        out["channels"][pid] = {
            "output": nm,
            "csv_fit": {"amp": mine["amp"], "phase_deg": mine["phase_deg"],
                        "offset": mine["offset"]},
            "measure": {"amp": ch["amp"], "phase_deg": ch.get("phase_deg")},
            "diff": {"amp_abs": d_amp, "amp_rel": r_amp, "phase_deg": d_ph},
        }
        worst_amp = max(worst_amp, r_amp or 0.0)
        worst_ph = max(worst_ph, d_ph)

    out["checks"]["recompute"] = {
        "source_freq": src_f, "skip_ratio": o.skip,
        "worst_amp_rel": worst_amp, "worst_phase_deg": worst_ph,
        "consistent": worst_amp < 1e-6 and worst_ph < 1e-6,
    }
    out["checks"]["sim_record"] = {
        "analysis": rec.get("analysis"), "state": rec.get("state"),
        "n": rec.get("n"), "outputs": rec.get("outputs"),
        "timing": rec.get("timing"), "topology_kind": (rec.get("topology") or {}).get("kind"),
    }
    out["ok"] = bool(out["checks"]["recompute"]["consistent"])
    txt = json.dumps(out, ensure_ascii=False, indent=2)
    if o.json:
        with open(o.json, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    print(txt)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
