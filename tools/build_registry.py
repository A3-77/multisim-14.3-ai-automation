# -*- coding: utf-8 -*-
"""离线扫描 donor，生成 `registry/components.json`（ComponentSpec 注册表）。

为什么要这一步
--------------
`circuit_ir.SUPPORTED` 原来是手写的 5 条常量。加一种元件就要人工去 .ms14 里
翻引脚名、猜 SPICE 模板 —— 而这些东西 donor 里本来就写着，手抄只会抄错。

所以拆成两件事：

    build_registry.py   离线扫一遍 donor，把"元件长什么样"抽出来存成 JSON
    registry.py         运行时只读 JSON，不碰 .ms14、不碰 Multisim、不碰数据库

扫描一次十几秒到几分钟，产物入库。之后 Agent 运行时完全不依赖 Multisim 安装
目录（除非某个 donor 只在安装目录里，见下面的 `donor.in_repo`）。

产物形状
--------
    {
      "schema": 1,
      "generated": "2026-10-27T17:00:00",
      "sources": [{"dir": ..., "tag": "corpus", "ms14": 13}, ...],
      "enabled": ["DIODE/1N4007G"],          <- 只有这里的才会被 IR 层接受
      "parts": {
        "DIODE/1N4007G": {
          "pins": ["A", "K"],                <- 引脚顺序（符号里的定义顺序）
          "pin_geometry": {"A": [x, y], ...},<- 引脚几何（donor 坐标）
          "pin_extent": [w, h],              <- 引脚包围盒，用来判水平/竖直
          "orientation": "horizontal",
          "spice_template": "d%p %tA %tK %m",
          "n_params": 0,                     <- 参数槽数，0 表示型号决定一切
          "refdes_prefix": "D",
          "donor": {"file": ..., "refdes": "D1", "in_repo": false},
          "n_donors": 6
        }
      }
    }

**"193 种 donor 存在" ≠ "193 种已支持"。** `parts` 是"目录"，`enabled` 是"闸门"。
只有进 `enabled` 的才会被 `circuit_ir.SUPPORTED` 接受，而进 `enabled` 的前提是
走完五步验证（GUI 放置 / 建最小 ms14 / 提取结构 / 重新组装 / 真机仿真对得上）。

用法
----
    python tools/build_registry.py                  # 扫全量，写 registry/components.json
    python tools/build_registry.py --only DIODE     # 只扫某个 family（调试用）
    python tools/build_registry.py --keep-enabled   # 保留已有的 enabled 列表
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import msbuild  # noqa: E402

OUT = os.path.join(ROOT, "registry", "components.json")

# 扫描顺序 = 优先级。corpus 在仓库里，优先用它，这样换机器也能复现。
SOURCES = [
    (os.path.join(ROOT, "corpus", "samples14"), "corpus"),
    (msbuild.INSTALL_SAMPLES, "install_samples"),
]

_PREFIX_RE = re.compile(r"^([A-Za-z_]+?)\d+$")
# Multisim 在属性字符串里用 `@@XXX@@` 当控制标记，实测见过 `@@WB_NL@@`（换行）。
# 它不是 SPICE 模板的一部分，存进 registry 前必须剥掉，否则下游按空格切分会切错。
_MARK_RE = re.compile(r"@@[A-Za-z_]+@@")


def spice_template(comp):
    """SPICE 模板串（Attributes[1] 里的第一条 String）。

    `d%p %tA %tK %m` 这种写法里，%p 是位号，%tX 是"引脚 X 的节点"。
    模板按**引脚名**引用，所以引脚顺序不影响正确性 —— 但读出来存着，
    以后要做"这个元件能不能当子电路"判断时用得上。
    """
    attrs = comp.find("Attributes")
    if attrs is None or len(attrs) < 2:
        return None
    for k in attrs[1].iter():
        s = k.get("String")
        if s:
            s = _MARK_RE.sub("", s.replace("&ASC", "")).strip()
            return s or None
    return None


def refdes_prefix(refdes, family):
    """从 donor 位号推前缀（D1 -> D）。推不出来再退到 family 首字母。"""
    m = _PREFIX_RE.match(refdes or "")
    if m:
        return m.group(1)
    stem = re.sub(r"\d+$", "", refdes or "")
    if stem:
        return stem
    return (family or "X")[:1].upper()


def _rel(path):
    """仓库内的路径存成相对路径（换机器/换盘符也能用），仓库外的保持绝对。"""
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:            # Windows 跨盘符
        return path
    if rel.startswith(".."):
        return path
    return rel.replace("\\", "/")


def describe(circuit, comp, path, tag):
    """把一个 donor 元件描述成 ComponentSpec 的核心字段。"""
    ciid = comp["ciid"]
    info = circuit.pin_info(ciid)

    # pin_info 按 CIITPinSymbolComp 在符号里的出现顺序返回（Python 3.7+ 的
    # dict 保序），这就是"引脚顺序"，不用另外排序。
    names = [n for n in info if info[n].get("xy")]
    geom = {n: [round(float(info[n]["xy"][0]), 3),
                round(float(info[n]["xy"][1]), 3)] for n in names}
    if geom:
        xs = [g[0] for g in geom.values()]
        ys = [g[1] for g in geom.values()]
        extent = [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)]
    else:
        extent = [0.0, 0.0]
    orientation = ("horizontal" if extent[0] >= extent[1]
                   else "vertical") if names else None

    return {
        "family": comp["family"],
        "part": comp["part"],
        "pins": names,
        "pin_geometry": geom,
        "pin_extent": extent,
        "orientation": orientation,
        "spice_template": spice_template(comp["comp"]),
        "n_params": len(circuit.params(comp["comp"])),
        "refdes_prefix": refdes_prefix(comp["refdes"], comp["family"]),
        "donor": {"file": _rel(path), "refdes": comp["refdes"],
                  "in_repo": tag == "corpus"},
        "n_donors": None,          # 后面统计时补
    }


def scan(only=None, verbose=True):
    """扫全部 donor，返回 (parts, sources)。parts 的键是 "FAMILY/PART"。"""
    parts = {}
    sources = []
    seen_ms14 = 0
    t0 = time.time()

    for d, tag in SOURCES:
        if not os.path.isdir(d):
            sources.append({"dir": _rel(d), "tag": tag, "ms14": 0,
                            "skipped": "目录不存在"})
            if verbose:
                print("  [跳过] %s（不存在）" % d)
            continue
        n_file = 0
        for p in msbuild._iter_ms14(d):
            n_file += 1
            seen_ms14 += 1
            try:
                c = msbuild.load_donor(p)
            except Exception as e:
                if verbose:
                    print("  [坏文件] %s: %s" % (os.path.basename(p), e))
                continue
            for comp in c.components():
                fam, part = comp["family"], comp["part"]
                if not fam or not part or not comp["refdes"]:
                    continue
                if only and fam.upper() != only.upper():
                    continue
                key = "%s/%s" % (fam, part)
                # 已有条目就只累加 donor 数量：扫描顺序决定了用谁当主 donor
                # （corpus 优先，换机器也能复现）
                if key in parts:
                    parts[key]["n_donors"] += 1
                    continue
                try:
                    spec = describe(c, comp, p, tag)
                except Exception as e:
                    if verbose:
                        print("  [跳过] %s [%s]: %s" % (key, comp["refdes"], e))
                    continue
                spec["n_donors"] = 1
                parts[key] = spec
        sources.append({"dir": _rel(d), "tag": tag, "ms14": n_file})
        if verbose:
            print("  %-16s %3d 个 .ms14  累计 %d 种元件  %.1fs"
                  % (tag, n_file, len(parts), time.time() - t0))
    return parts, sources


def main(argv=None):
    ap = argparse.ArgumentParser(description="扫描 donor 生成 registry/components.json")
    ap.add_argument("--only", help="只扫某个 family（如 DIODE）")
    ap.add_argument("--keep-enabled", action="store_true",
                    help="保留现有 registry 里的 enabled 列表")
    ap.add_argument("-o", "--out", default=OUT)
    opts = ap.parse_args(argv)

    enabled = []
    if opts.keep_enabled and os.path.isfile(opts.out):
        with open(opts.out, encoding="utf-8") as f:
            enabled = list((json.load(f) or {}).get("enabled") or [])
        print("保留 enabled：%s" % (", ".join(enabled) or "（空）"))

    print("扫描 donor ...")
    parts, sources = scan(only=opts.only)

    for k in enabled:
        if k not in parts:
            print("  !! enabled 里的 %r 在本次扫描里没找到，仍保留（可能是 --only）" % k)

    doc = {
        "schema": 1,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "generator": "tools/build_registry.py",
        "note": ("parts 是 donor 目录（存在 ≠ 已支持）；enabled 才是 IR 层的闸门。"
                 "进 enabled 必须走完五步验证。"),
        "sources": sources,
        "enabled": enabled,
        "parts": dict(sorted(parts.items())),
    }
    os.makedirs(os.path.dirname(os.path.abspath(opts.out)), exist_ok=True)
    with open(opts.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    print("\n写出 %s" % opts.out)
    print("  元件 %d 种  |  .ms14 %d 个  |  已启用 %d 种"
          % (len(parts), sum(s.get("ms14") or 0 for s in sources), len(enabled)))

    fams = {}
    for k in parts:
        fams.setdefault(k.split("/")[0], 0)
        fams[k.split("/")[0]] += 1
    print("  按 family 分布（前 12）：")
    for fam, n in sorted(fams.items(), key=lambda kv: -kv[1])[:12]:
        print("    %-24s %d" % (fam, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
