# -*- coding: utf-8 -*-
"""阶段3 实验：静态电路到底在哪一刻读得到数。

上一轮结论（out/dc/dc_experiment.json）：
    探针在打开时就注册上了 ['V(探针1)', 'V(探针2)']，
    但 transient 和 DoDCOperatingPoint 之后 GetOutputData 都报 E_FAIL。

假设：静态电路算得太快，**跑完就停了**，缓冲区随之清空，
等我们 wait 完再去 read，数据已经没了。AC 电路因为真的要算 6ms，读的时候还在跑。

这个脚本把几种"抢在停之前读"的时序各试一遍，每种开一个新的电路对象，
互不污染：

    S1  run(0.006, pause=True) -> 立刻 read        （暂停而不是停）
    S2  RunSimulationUntilNextOutput() -> 立刻 read
    S3  DoDCOperatingPoint -> 紧轮询 state==Running 时立刻 read
    S4  run(0.006) -> 立刻 read（不 wait，对照组）

必须 32 位 Python：
    runtime\\py32\\python.exe -u tools/dc_strategies.py
"""
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

MS14 = os.path.join(ROOT, "out", "dc", "dc_min.ms14")
OUT = os.path.join(ROOT, "out", "dc", "dc_strategies.json")


def read_all(circ, outs):
    got = {}
    for nm in outs:
        try:
            t, v = circ.read(nm)
            got[nm] = {"n": len(v),
                       "min": min(v) if v else None,
                       "max": max(v) if v else None,
                       "first": v[0] if v else None,
                       "last": v[-1] if v else None}
        except Exception as e:
            got[nm] = {"err": str(e)}
    return got


def fresh(app):
    circ = app.open(MS14)
    outs = list(circ.probes())
    return circ, outs


def s1_pause(app, outs_hint=None):
    circ, outs = fresh(app)
    n = 1200
    for nm in outs:
        circ.request_output(nm, 200000.0, n, method=msc.Interp.Linear)
    circ.run(0.006, pause=True)
    st = str(circ.state)
    data = read_all(circ, outs)          # 不等，直接读
    try:
        circ.stop()
    except Exception:
        pass
    return {"strategy": "S1 run(pause=True)", "state_after_run": st,
            "read": data, "outputs": outs}


def s2_until_output(app):
    circ, outs = fresh(app)
    for nm in outs:
        circ.request_output(nm, 200000.0, 1200, method=msc.Interp.Linear)
    circ.run_until_next_output()
    st = str(circ.state)
    data = read_all(circ, outs)
    try:
        circ.stop()
    except Exception:
        pass
    return {"strategy": "S2 RunSimulationUntilNextOutput", "state_after_run": st,
            "read": data, "outputs": outs}


def s3_dc_op_fast(app):
    circ, outs = fresh(app)
    timeline = []
    try:
        circ._c.DoDCOperatingPoint(msc._bstr_array(outs))
        timeline.append(("call_ok", str(circ.state)))
    except Exception as e:
        timeline.append(("call_err", str(e)))
    # 紧轮询：state 一变 Running 就读
    data = None
    for _ in range(2000):
        st = circ.state
        if st == msc.SimState.Running:
            timeline.append(("running", "read"))
            data = read_all(circ, outs)
            break
        if st == msc.SimState.Stopped and len(timeline) > 2:
            break
        timeline.append(("poll", str(st)))
    if data is None:
        data = read_all(circ, outs)
    try:
        circ.stop()
    except Exception:
        pass
    # timeline 去掉重复的 poll 记录，只留状态变化
    compact = []
    for item in timeline:
        if compact and item[0] == "poll" and compact[-1][0] == "poll" \
                and compact[-1][1] == item[1]:
            continue
        compact.append(item)
    return {"strategy": "S3 DoDCOperatingPoint + 紧轮询", "timeline": compact,
            "read": data, "outputs": outs}


def s4_run_then_read(app):
    circ, outs = fresh(app)
    for nm in outs:
        circ.request_output(nm, 200000.0, 1200, method=msc.Interp.Linear)
    circ.run(0.006, pause=False)
    st = str(circ.state)
    data = read_all(circ, outs)
    try:
        circ.stop()
    except Exception:
        pass
    return {"strategy": "S4 run(不暂停) -> 立刻 read", "state_after_run": st,
            "read": data, "outputs": outs}


def main():
    global MS14
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="S1,S2,S3,S4")
    ap.add_argument("--ms14", default=MS14)
    args = ap.parse_args()
    MS14 = args.ms14

    subprocess.run(["taskkill", "/F", "/IM", "multisim.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    app = msc.Multisim()
    print("=" * 78)
    print("静态取数时序实验：%s" % MS14)
    print("=" * 78)

    wanted = [s.strip().upper() for s in args.only.split(",") if s.strip()]
    table = {"S1": s1_pause, "S2": s2_until_output,
             "S3": s3_dc_op_fast, "S4": s4_run_then_read}
    results = []
    for key in wanted:
        fn = table[key]
        print("\n--- %s ..." % key)
        sys.stdout.flush()
        try:
            r = fn(app)
        except Exception as e:
            r = {"strategy": key, "fatal": str(e)}
        results.append(r)
        print("--- %s" % r.get("strategy"))
        for k in ("state_after_run", "timeline"):
            if k in r:
                print("  %s: %s" % (k, r[k]))
        print("  read: %s" % r.get("read"))
        sys.stdout.flush()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"ms14": MS14, "results": results}, f, ensure_ascii=False, indent=2)
    print("\n证据 -> %s" % OUT)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
