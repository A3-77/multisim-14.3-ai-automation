# -*- coding: utf-8 -*-
"""ComponentSpec 注册表的**运行时**读取层（纯 Python，不碰 Multisim）。

职责边界
--------
    build_registry.py   离线扫描 donor -> 写 registry/components.json（重活）
    registry.py         读那份 JSON，给 circuit_ir / circuit_session 用（轻活）

运行时只读一个 JSON 文件：
  * 不 import msc / win32com（64 位 Python 也能用）
  * 不打开任何 .ms14（除非调用方显式要校验 donor 是否存在）
  * 不访问元件数据库（那是 14.3.0 的坑，14.3.3 修了，但项目本来就不依赖它）

两个概念必须分清
----------------
    parts      registry 里"扫到过"的全部元件（193 种）
    enabled    IR 层真正接受的元件（现在只有 DIODE/1N4007G）

`spec()` 对两者一视同仁地返回数据（做调查时有用）；
`ir_spec()` 只对 enabled 的返回东西 —— **这是闸门**。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTRY_PATH = os.path.join(ROOT, "registry", "components.json")

_CACHE = {}


def _doc():
    """读并缓存 components.json。文件不存在就当成空表（不抛错）。"""
    if "doc" in _CACHE:
        return _CACHE["doc"]
    doc = {"parts": {}, "enabled": [], "sources": [], "schema": 0}
    if os.path.isfile(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, encoding="utf-8") as f:
                doc = json.load(f) or doc
        except Exception:
            pass
    doc.setdefault("parts", {})
    doc.setdefault("enabled", [])
    _CACHE["doc"] = doc
    return doc


def reload():
    """丢掉缓存重读（改完 JSON 不想重启进程时用）。"""
    _CACHE.clear()
    return _doc()


def key(family, part):
    return "%s/%s" % (family, part)


def enabled_keys():
    """enabled 列表（"FAMILY/PART" 字符串），保持文件里的顺序。"""
    return list(_doc().get("enabled") or [])


def enabled():
    """enabled 列表拆成 [(family, part), ...]。"""
    out = []
    for k in enabled_keys():
        fam, _, part = str(k).partition("/")
        if fam and part:
            out.append((fam, part))
    return out


def spec(family, part):
    """扫到过的元件描述（不管是否 enabled）。没有返回 None。"""
    return (_doc().get("parts") or {}).get(key(family, part))


def all_keys():
    return list((_doc().get("parts") or {}).keys())


def donor_path(entry):
    """donor 的 .ms14 绝对路径。相对路径按仓库根解析（入库时存相对路径）。"""
    p = ((entry or {}).get("donor") or {}).get("file")
    if not p:
        return None
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(ROOT, p))


def donor_ready(entry):
    """donor 文件在不在。不在时编译会失败，所以要能提前问。"""
    p = donor_path(entry)
    return bool(p and os.path.isfile(p))


def ir_spec(family, part):
    """**闸门**：只有 enabled 的元件才返回 IR 层能用的 spec。

    返回的形状与 `circuit_ir.SUPPORTED` 的条目一致，另带两个诊断字段：
        spice_template   从 donor 读出来的 SPICE 模板（只读旁证）
        origin           "registry"（区别于手写的 5 条 legacy）
        donor            {"file": ..., "refdes": ...}，编译时显式指定 donor
    """
    if (family, part) not in set(enabled()):
        return None
    e = spec(family, part)
    if not e:
        return None
    pins = tuple(e.get("pins") or ())
    if not pins:
        return None
    d = {"pins": pins, "aliases": {}, "origin": "registry",
         "spice_template": e.get("spice_template"),
         "prefix": e.get("refdes_prefix")}
    dpath = donor_path(e)
    if dpath and (e.get("donor") or {}).get("refdes"):
        d["donor"] = {"file": dpath, "refdes": e["donor"]["refdes"],
                      "in_repo": bool(e["donor"].get("in_repo"))}
    return d


def summary():
    """一行摘要，给 CLI / 报告用。"""
    d = _doc()
    return {"schema": d.get("schema"), "generated": d.get("generated"),
            "parts": len(d.get("parts") or {}),
            "enabled": len(d.get("enabled") or []),
            "sources": d.get("sources") or []}


if __name__ == "__main__":
    import sys
    s = summary()
    print("registry: %s" % REGISTRY_PATH)
    print("  生成于 %s | 元件 %d 种 | 已启用 %d 种"
          % (s["generated"], s["parts"], s["enabled"]))
    for src in s["sources"]:
        print("  %-16s %3d 个 .ms14  %s"
              % (src.get("tag"), src.get("ms14") or 0, src.get("dir")))
    print("  已启用：%s" % (", ".join(enabled_keys()) or "（无）"))
    if len(sys.argv) > 1:
        fam, _, part = sys.argv[1].partition("/")
        e = spec(fam, part)
        if not e:
            print("  找不到 %s" % sys.argv[1])
            sys.exit(1)
        print(json.dumps(e, ensure_ascii=False, indent=2))
