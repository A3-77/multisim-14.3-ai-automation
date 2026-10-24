# -*- coding: utf-8 -*-
"""从 MSInterface.dll 的类型库导出完整 API 参考（Markdown）。用 64 位 Python 跑，仅解析类型库。"""
import os
import comtypes.client as cc

DLL = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\MSInterface.dll"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "api.md")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

m = cc.GetModule(DLL)

TYPEMAP = {
    "BSTR": "str", "LP_BSTR": "str", "c_double": "float", "LP_c_double": "float",
    "c_long": "int", "LP_c_long": "int", "VARIANT_BOOL": "bool",
    "LP_VARIANT_BOOL": "bool", "tagVARIANT": "variant", "LP_tagVARIANT": "variant",
    "int64": "int", "uint8": "int", "uint16": "int", "uint64": "int",
}


def tname(t):
    s = getattr(t, "__name__", str(t))
    s = s.replace("comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0.", "")
    s = s.replace("comtypes.automation.", "").replace("comtypes._post_coinit.", "")
    if s.startswith("LP_POINTER("):
        inner = s[len("LP_POINTER("):-1]
        return TYPEMAP.get(inner, inner)
    return TYPEMAP.get(s, s)


def params(x):
    out = []
    for flag, argtype in zip([f[0] for f in x.paramflags], x.argtypes):
        nm = ""
        for f in x.paramflags:
            pass
        out.append((flag, tname(argtype)))
    # 名字从 paramflags 里取
    names = [f[1] for f in x.paramflags]
    res = []
    for (flag, t), nm in zip(out, names):
        kind = "out" if flag & 2 else "in"
        res.append("%s: %s%s" % (nm, t, "" if kind == "in" else "  ← 输出"))
    return res


lines = ["# Multisim Automation API 参考", "",
         "从 `MSInterface.dll` 的类型库直接导出，未做人工增删。",
         "ProgID：`MultisimInterface.MultisimApp` / `MultisimInterface.MultisimCircuit`。",
         "官方文档：https://www.ni.com/docs/zh-CN/bundle/multisim/page/topics/enumoutputs.html", ""]

for iname, label in (("IMultisimApp", "应用对象 IMultisimApp"), ("IMultisimCircuit", "电路对象 IMultisimCircuit")):
    it = getattr(m, iname)
    lines.append("## %s" % label)
    lines.append("")
    lines.append("| 成员 | 参数 | 说明 |")
    lines.append("| --- | --- | --- |")
    for x in it._methods_:
        nm = x.name.lstrip("_")
        kind = ""
        if x.name.startswith("_get_"):
            kind = "（只读属性）"
        elif x.name.startswith("_set_"):
            kind = "（只写属性）"
        doc = (x.doc or "").replace("|", "\\|")
        lines.append("| `%s`%s | %s | %s |" % (nm, kind, "; ".join(params(x)) or "—", doc))
    lines.append("")

lines.append("## 枚举")
lines.append("")
for name in ("SimulationState", "SimulationIOType", "SimulationInterpolation", "SweepType",
             "ComponentType", "CircuitParameterLevel", "ExportFormat", "CircuitImageFormat"):
    o = getattr(m, name, None)
    if o is None:
        continue
    mem = getattr(o, "__members__", None)
    if mem:
        lines.append("- **%s**：%s" % (name, "、".join("%s=%d" % (k, v) for k, v in mem.items())))
    else:
        lines.append("- **%s**：`%s`" % (name, o))

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("written", OUT, len("\n".join(lines)), "chars")
