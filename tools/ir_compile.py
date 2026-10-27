# -*- coding: utf-8 -*-
"""Circuit IR -> .ms14 编译器。

**只调用已经通过验收的底层 API**，一行底层机制都不改：
    Assembler.add_part()      统一元件入口（含 pin-anchor 定位）
    Assembler.connect()       建网络 + 画导线
    Assembler.add_probe_ext() 新式探针（唯一 LocalName）
    Assembler.net_vertices()  取网络导线顶点
    Assembler.save()          走 mssafe 序列化 + DCL 打包

本模块负责的三件事（都是"翻译"，不是"实现"）：
    1. 引脚名解析：IR 的 "V1.+" / "R1.1" -> add_part 返回的实际引脚名
    2. 接地元件位号映射：IR 里叫 GND1（可读、可被连接引用），
       但 Multisim 里所有地都必须是位号 "0"
    3. 探针落点：IR 只说"探针在 net out 上"，编译器去该网络里挑一个导线顶点

用法：
    import ir_compile
    rep = ir_compile.compile_ir("examples/rc_lowpass.ir.json",
                                "out/ref/rc_lowpass_ir.ms14")
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402
import msbuild             # noqa: E402


class CompileError(Exception):
    pass


def _split_pin(token):
    """'R1.1' -> ('R1', '1')；'V1.+' -> ('V1', '+')。"""
    ref, dot, pin = str(token).partition(".")
    if not dot or not ref or not pin:
        raise CompileError("引脚写法不对：%r（应为 '位号.引脚'，如 'R1.1'）" % token)
    return ref, pin


def _resolve_pin(comp, pin, actual_names):
    """把 IR 层引脚名翻译成 donor 实际引脚名，并确认它真的存在。

    别名来自 circuit_ir.SUPPORTED[part]["aliases"]（例如源的 '+' -> '1'）。
    翻译完还要在 add_part 实际返回的引脚名里查一遍 —— 这一步是硬的，
    别名表写错了会在这里立刻暴露，而不是等 Multisim 报"输出未找到"。
    """
    spec = irmod.SUPPORTED.get((comp.family, comp.part)) or {}
    real = (spec.get("aliases") or {}).get(pin, pin)
    if real not in actual_names:
        raise CompileError(
            "%s（%s/%s）没有引脚 %r%s。实际引脚：%s"
            % (comp.refdes, comp.family, comp.part, pin,
               ("（别名 -> %r）" % real) if real != pin else "",
               sorted(actual_names)))
    return real


def _xy_key(xy):
    return (round(float(xy[0]), 3), round(float(xy[1]), 3))


def _pick_probe_xy(vs, net, pin_at, ir):
    """在网络的所有导线顶点里挑一个探针落点。

    **默认沿用 v0.1 以来的取法**：有拐点就用拐点 `vs[1]`，否则用 `vs[0]`。
    已验收的电路全靠这个位置，不能动。

    只有一种情况要换点：那个坐标**正好是别的元件的引脚**。v0.9 做二极管时
    实测到了：探针落在二极管阴极（属于另一条网络）上，`EnumOutputs` 里直接
    少一个通道 —— 表现是"只有一个探针有数据"，而电路本身完全正确。
    这种情况下改挑一个属于本网络的引脚顶点。
    """
    cur = vs[1] if len(vs) >= 3 else vs[0]
    owner = pin_at.get(_xy_key(cur))
    if owner is None:
        return cur

    own = set()
    for refdes, pin in net.refs():
        comp = ir.component(refdes)
        if comp is None:
            continue
        own.add((refdes, irmod._norm_pin(comp, pin) or pin))
    if owner in own:
        return cur

    for xy in vs:                       # 优先：本网络自己的引脚
        o = pin_at.get(_xy_key(xy))
        if o is not None and o in own:
            return xy
    for xy in vs:                       # 其次：压根不是引脚的自由拐点
        if _xy_key(xy) not in pin_at:
            return xy
    return cur                          # 都躲不开就保持原样，并在报告里留痕


def compile_ir(src, out_path, verbose=True):
    """把 IR（路径或 CircuitIR 对象）编译成 .ms14，返回编译报告 dict。

    编译前先跑 CircuitIR.validate()。校验不过就直接抛 CompileError，
    **一个字节的 .ms14 都不会写出来** —— 错误必须在落盘之前发现。
    """
    c = irmod.CircuitIR.load(src) if isinstance(src, (str, bytes, os.PathLike)) else src

    errs = c.validate()
    if errs:
        raise CompileError("IR 校验失败（%d 项），未生成任何文件：\n  - %s"
                           % (len(errs), "\n  - ".join(errs)))
    if verbose:
        for w in c.warnings():
            print("  [警告] %s" % w)

    a = msbuild.Assembler()
    ciid_of = {}          # IR refdes -> CiID
    ports_of = {}         # IR refdes -> {实际引脚名}
    report = {"ir": c.name, "out": os.path.abspath(out_path),
              "components": [], "nets": [], "probes": []}

    # ---------- 1) 元件 ----------
    for comp in c.components:
        key = (comp.family, comp.part)
        if key not in irmod.SUPPORTED:
            raise CompileError(
                "%s: 元件 %s/%s 不在已验证白名单里。可用：%s"
                % (comp.refdes, comp.family, comp.part,
                   ", ".join("%s/%s" % k for k in irmod.SUPPORTED)))

        # 地的位号在 Multisim 里必须是 "0"（所有地共用），IR 里的 GND1 只是
        # 给连接引用用的可读名字。
        ms_refdes = "0" if comp.part == "GROUND" else comp.refdes

        x = y = None
        if comp.position:
            if len(comp.position) != 2:
                raise CompileError("%s: position 必须是 [x, y]" % comp.refdes)
            x, y = float(comp.position[0]), float(comp.position[1])

        # registry 来的元件带显式 donor：**不用 find_part() 去猜**。
        # 手写的 5 条没有 donor 字段，走的还是原来的 find_part 路径 ——
        # 所以这 5 种元件的行为一个字节都没变。
        extra = {}
        donor = (irmod.SUPPORTED.get(key) or {}).get("donor")
        if donor:
            dpath = donor.get("file")
            if not dpath or not os.path.isfile(dpath):
                raise CompileError(
                    "%s: registry 里记的 donor 找不到：%r\n"
                    "  donor 可能被移动或删除了。跑 tools/build_registry.py 重建 registry，"
                    "或用 add_part(donor_path=...) 显式指定。"
                    % (comp.refdes, dpath))
            extra = {"donor_path": dpath, "donor_refdes": donor.get("refdes")}

        ciid, ports = a.add_part(comp.family, comp.part, ms_refdes,
                                 value=comp.value, x=x, y=y,
                                 params=comp.params or None, **extra)
        ciid_of[comp.refdes] = ciid
        ports_of[comp.refdes] = {name for _pid, name in ports}
        report["components"].append({
            "refdes": comp.refdes, "ms_refdes": ms_refdes,
            "family": comp.family, "part": comp.part,
            "value": comp.value, "ciid": ciid,
            "pins": sorted(ports_of[comp.refdes]),
            "donor": a.last_part.get("donor") if hasattr(a, "last_part") else None,
            "donor_refdes": (a.last_part or {}).get("donor_refdes")
            if hasattr(a, "last_part") else None,
            "origin": (irmod.SUPPORTED.get(key) or {}).get("origin") or "legacy",
            "spice_template": (irmod.SUPPORTED.get(key) or {}).get("spice_template"),
        })
        if verbose:
            print("  元件 %-6s -> CiID=%-10s 引脚=%s"
                  % (comp.refdes, ciid, sorted(ports_of[comp.refdes])))

    # ---------- 2) 网络 ----------
    node_of = {}
    for net in c.nets:
        members = []
        for refdes, pin in net.refs():
            if refdes not in ciid_of:
                raise CompileError("网络 %r 引用了不存在的元件 %r" % (net.name, refdes))
            comp = c.component(refdes)
            real = _resolve_pin(comp, pin, ports_of[refdes])
            members.append((ciid_of[refdes], real))
        if len(members) < 2:
            raise CompileError("网络 %r 只有 %d 个引脚，至少要 2 个"
                               % (net.name, len(members)))
        node_id = a.connect(members, name=net.name)
        node_of[net.name] = node_id
        report["nets"].append({"name": net.name, "node": node_id,
                               "pins": list(net.pins)})
        if verbose:
            print("  网络 %-6s -> CiID=%-10s %s" % (net.name, node_id, net.pins))

    # ---------- 3) 探针 ----------
    # 引脚坐标表：探针落点不能和"别的元件的引脚"重合（见 _pick_probe_xy）
    pin_at = {}
    for comp in c.components:
        ciid = ciid_of.get(comp.refdes)
        if ciid is None:
            continue
        for name, info in a.c.pin_info(ciid).items():
            xy = info.get("xy")
            if xy:
                pin_at[_xy_key(xy)] = (comp.refdes, name)

    for i, pr in enumerate(c.probes, 1):
        if pr.kind != "V":
            raise CompileError("%s: 目前只支持电压探针（kind='V'）" % pr.refdes)
        if pr.net:
            if pr.net not in node_of:
                raise CompileError("%s: 探针目标网络 %r 不存在" % (pr.refdes, pr.net))
            vs = a.net_vertices(node_of[pr.net])
            if not vs:
                raise CompileError("%s: 网络 %r 上没有导线顶点，探针无处可放"
                                   % (pr.refdes, pr.net))
            xy = _pick_probe_xy(vs, c.net(pr.net), pin_at, c)
            target = {"net": pr.net, "node": node_of[pr.net],
                      "vertices": len(vs),
                      "at_pin": list(pin_at.get(_xy_key(xy)) or ()) or None}
        elif pr.at:
            if len(pr.at) != 2:
                raise CompileError("%s: at 必须是 [x, y]" % pr.refdes)
            xy = (float(pr.at[0]), float(pr.at[1]))
            target = {"at": list(xy)}
        else:
            raise CompileError("%s: 探针必须给 net 或 at" % pr.refdes)

        elec, draw = a.add_probe_ext(xy[0], xy[1], index=i)
        report["probes"].append({
            "refdes": pr.refdes, "index": i, "ciid": elec, "draw": draw,
            "xy": [xy[0], xy[1]], "local_name": a.last_probe["local_name"],
            **target,
        })
        if verbose:
            print("  探针 %-6s -> 序号%d  %s  LocalName=%s"
                  % (pr.refdes, i, target, a.last_probe["local_name"]))

    # ---------- 4) 写盘 ----------
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    n, _ = a.save(out_path)
    report["bytes"] = n
    report["simulation"] = {
        "analysis": c.simulation.analysis, "start": c.simulation.start,
        "stop": c.simulation.stop, "step": c.simulation.step,
        "sample_rate": c.simulation.sample_rate,
    }

    rep_path = os.path.splitext(out_path)[0] + ".compile.json"
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    report["report_path"] = rep_path
    if verbose:
        print("  写出 %s (%d 字节)" % (out_path, n))
        print("  编译报告 %s" % rep_path)
    return report


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Circuit IR -> .ms14")
    ap.add_argument("ir", help="IR JSON 路径")
    ap.add_argument("-o", "--out", required=True, help="输出 .ms14 路径")
    args = ap.parse_args()
    print("编译 %s" % args.ir)
    compile_ir(args.ir, args.out)


if __name__ == "__main__":
    main()
