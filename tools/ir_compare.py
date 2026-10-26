# -*- coding: utf-8 -*-
"""结构比对两个 .ms14：元件清单、网络成员、探针数量。

只做静态比对（不启动 Multisim），用来回答：
「IR 编译出来的电路，和手写 add_part 拼出来的，是不是同一个电路？」

比较项：
    元件   (位号, family, part) 的集合
    网络   每个网络的引脚集合（引脚写成 "位号.引脚名"）
    探针   数量（名字由 Multisim 运行时生成，不参与比较）
    参数   CiaParamList/parameters 的人类可读值（元件值）

用法：
    python tools/ir_compare.py out/ref/rc_lowpass.ms14 out/ref/rc_lowpass_ir.ms14
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel  # noqa: E402


def _main_value(c, comp):
    """取元件主参数的人类可读值（"&ASC1k" 这种），外加 doubles[1] 数值。

    不能直接用 Circuit.params()[0]：那个返回的是整块 Item 列表的第 0 项，
    原生虚拟元件的 doubles 是空的，拿到的会是 strings 里的占位符，比不出东西。
    """
    attrs = comp.find("Attributes")
    if attrs is None or len(attrs) <= 2:
        return None
    pl = attrs[2].find("CiaParamList")
    if pl is None:
        return None
    human = num = None
    ps = pl.find("parameters")
    if ps is not None:
        items = ps.findall("Item")
        if len(items) > 1:
            human = items[1].get("Value")
    ds = pl.find("doubles")
    if ds is not None:
        items = ds.findall("Item")
        if len(items) > 1:
            num = items[1].get("Value")
    return human or num


def fingerprint(path):
    c = msmodel.Circuit.load(path)
    refs = {x["ciid"]: x["refdes"] for x in c.components()}

    comps = {}
    for x in c.components():
        key = (x["refdes"], x["family"], x["part"])
        try:
            comps[key] = _main_value(c, x["comp"])
        except Exception:
            comps[key] = None

    nets = {}
    pm = {p["ciid"]: p for p in c.ports()}
    for nd in c.nodes():
        pins = []
        for pid in nd["ports"]:
            p = pm.get(pid)
            if p:
                pins.append("%s.%s" % (refs.get(p["component"], "?"), p["name"]))
        if pins:
            nets["|".join(sorted(pins))] = nd.get("name")

    probes = [e for e in c.elements if e.get("Class") == "CiProbeExtComp"]
    return {"comps": comps, "nets": nets, "probes": len(probes), "path": path}


def compare(a_path, b_path):
    A, B = fingerprint(a_path), fingerprint(b_path)
    ok = True

    print("=" * 74)
    print("结构比对")
    print("  A = %s" % a_path)
    print("  B = %s" % b_path)
    print("=" * 74)

    print("\n[元件]")
    ka, kb = set(A["comps"]), set(B["comps"])
    if ka == kb:
        print("  集合一致：%d 个元件" % len(ka))
    else:
        ok = False
        for k in sorted(ka - kb):
            print("  只在 A：%s" % (k,))
        for k in sorted(kb - ka):
            print("  只在 B：%s" % (k,))
    for k in sorted(ka & kb):
        va, vb = A["comps"][k], B["comps"][k]
        flag = "OK" if va == vb else "差异"
        if va != vb:
            ok = False
        print("  %-34s 值 A=%-12s B=%-12s %s" % (str(k), va, vb, flag))

    print("\n[网络]")
    na, nb = set(A["nets"]), set(B["nets"])
    if na == nb:
        print("  网络成员一致：%d 条" % len(na))
        for k in sorted(na):
            print("    %-40s (A:%s / B:%s)" % (k, A["nets"][k], B["nets"][k]))
    else:
        ok = False
        for k in sorted(na - nb):
            print("  只在 A：%s" % k)
        for k in sorted(nb - na):
            print("  只在 B：%s" % k)

    print("\n[探针]")
    print("  A=%d 个  B=%d 个  %s"
          % (A["probes"], B["probes"], "OK" if A["probes"] == B["probes"] else "不一致"))
    if A["probes"] != B["probes"]:
        ok = False

    print("\n" + "-" * 74)
    print("结论：%s" % ("结构等价" if ok else "存在差异"))
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(0 if compare(sys.argv[1], sys.argv[2]) else 1)
