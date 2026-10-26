# -*- coding: utf-8 -*-
"""P12：样例覆盖率统计 —— 185 个 (family, part) 里有多少能真的克隆进空白电路。

判定标准：在全新的 Assembler 里 add_part() 成功、且新元件
（CiComponent + CiPort + 绘图对象）落地、引脚符号 PortID 全部指向新端口。

产物：out/p12_coverage.json
"""
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

OUT = os.path.join(ROOT, "out", "p12_coverage.json")


def check(c, ciid, part=""):
    """克隆后的自检：元件在、端口在、符号在、PortID 绑定、有模型或 SPICE 模板。"""
    ports = {p["name"]: p["ciid"] for p in c.ports() if p["component"] == ciid}
    sym = c.symbol_of(ciid)
    if not ports:
        return False, "没有 CiPort"
    if sym is None:
        return False, "没有绘图对象"
    bound = set()
    for el in sym.iter("CIITPinSymbolComp"):
        v = el.get("PortID")
        if v in ports.values():
            bound.add(v)
    if len(bound) != len(ports):
        return False, "PortID 绑定 %d/%d" % (len(bound), len(ports))
    comp = c._item_of(ciid).find("CiComponent")
    at = comp.find("Attributes")
    tmpl = ""
    if at is not None and len(at) > 1:
        for e in at[1].iter("CiaSpiceTmpltExprt"):
            tmpl = e.get("String") or ""
    has_model = bool(comp.get("Model"))
    if not tmpl and not has_model:
        # 地/网络连接器本来就没有 SPICE 模板，不算缺陷
        if (part or "").upper() in ("GROUND", "DUMMY"):
            return True, "ok（无模板，属正常）"
        return False, "既无 SPICE 模板也无模型"
    return True, "ok"


def main():
    idx = msbuild.part_index()
    pairs = sorted(idx.items(), key=lambda kv: -len(kv[1]))
    print("组合总数: %d" % len(pairs))

    ok, bad, broken = [], [], []
    t0 = time.time()
    for (fam, part), cands in pairs:
        cache, ref = cands[0]
        rec = {"family": fam, "part": part, "occurrences": len(cands),
               "samples": len({c[0] for c in cands}),
               "donor": os.path.basename(cache), "donor_refdes": ref}
        try:
            msbuild.load_donor(cache)          # 先确认 donor 文件本身可读
        except Exception as e:
            rec["ok"] = False
            rec["reason"] = "donor 缓存损坏（XML 截断）：%s" % type(e).__name__
            broken.append(rec)
            print("  %-28s %-22s BROKEN %s" % (fam or "?", part or "?", rec["reason"]))
            continue
        try:
            a = msbuild.Assembler()
            ciid, _ = a.add_part(fam, part, "X1", value=None, x=100.0, y=100.0,
                                 donor_path=cache, donor_refdes=ref)
            good, why = check(a.c, ciid, part)
        except Exception as e:
            good, why = False, "%s: %s" % (type(e).__name__, e)
        rec["ok"] = good
        rec["reason"] = why
        (ok if good else bad).append(rec)
        print("  %-28s %-22s %-4s %s" % (fam or "?", part or "?",
                                         "OK" if good else "FAIL", why if not good else ""))

    # 缺口 top10：按在样例里出现的次数排（越常用越该优先补）
    bad_sorted = sorted(bad, key=lambda r: (-r["occurrences"], r["family"], r["part"]))
    gaps = sorted(bad + broken, key=lambda r: (-r["occurrences"], r["family"], r["part"]))
    res = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "corpus/samples_index.json",
        "samples_total": 108,
        "pairs_total": len(pairs),
        "pairs_clonable": len(ok),
        "pairs_failed": len(bad),
        "pairs_donor_broken": len(broken),
        "coverage_ratio": round(len(ok) / float(len(pairs)), 4) if pairs else 0,
        "coverage_ratio_readable": round(len(ok) / float(len(pairs) - len(broken)), 4)
        if pairs else 0,
        "occurrences_total": sum(len(v) for v in idx.values()),
        "occurrences_clonable": sum(r["occurrences"] for r in ok),
        "top10_gaps": [{"family": r["family"], "part": r["part"],
                        "occurrences": r["occurrences"],
                        "samples": r["samples"], "reason": r["reason"]}
                       for r in gaps[:10]],
        "clonable": [{"family": r["family"], "part": r["part"],
                      "occurrences": r["occurrences"]} for r in ok],
        "failed": [{"family": r["family"], "part": r["part"],
                    "occurrences": r["occurrences"], "reason": r["reason"]}
                   for r in bad_sorted],
        "donor_broken": [{"family": r["family"], "part": r["part"],
                          "occurrences": r["occurrences"], "donor": r["donor"],
                          "reason": r["reason"]} for r in broken],
    }
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print()
    print("可克隆 %d / %d = %.1f%%   失败 %d    donor 损坏 %d   （耗时 %.1fs）"
          % (len(ok), len(pairs), 100.0 * len(ok) / max(1, len(pairs)),
             len(bad), len(broken), time.time() - t0))
    print("已写入", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
