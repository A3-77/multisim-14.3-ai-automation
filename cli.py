# -*- coding: utf-8 -*-
"""
cli.py —— 命令行入口。用 run.bat 调用即可，例如：

    run.bat                     # 自检：能不能连上
    run.bat info  samples\\7812.ms12
    run.bat sim   samples\\7812.ms12 --seconds 0.02 --out out\\run.csv
    run.bat ac    samples\\V-I变换.ms12 --start 10 --stop 100000
    run.bat img   samples\\7812.ms12 --out out\\shot.png
    run.bat demo
"""

import os
import sys
import argparse

# 自带的 32 位 Python 用的是 ._pth 隔离模式，脚本目录不在 sys.path 里，手动加一下
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import msc
from msc import Multisim, CompType, IOType, SweepType, ImgFmt, ExportFmt


def cmd_selftest(args):
    msc.selftest()
    return 0


def cmd_info(args):
    with Multisim() as ms:
        c = ms.open(args.file)
        print("电路名 :", c.name)
        print("源文件 :", c.file)
        print("元件   :", ", ".join(c.components()) or "（空）")
        print("探针   :", ", ".join(c.probes()) or "（无 —— 没有探针就没法取波形）")
        print("变体   :", ", ".join(c.variants()) or "（无）")
        print("参数   :", ", ".join(c.params()) or "（无）")
        rlc = []
        for nm in c.components():
            try:
                rlc.append("%s=%g" % (nm, c.rlc(nm)))
            except Exception:
                pass
        if rlc:
            print("RLC    :", ", ".join(rlc))
    return 0


def cmd_sim(args):
    with Multisim() as ms:
        c = ms.open(args.file)
        probes = c.probes()
        if not probes:
            print("这个电路里没有探针，取不到数据。先在 Multisim 里放探针再存盘。")
            return 2
        print("探针:", ", ".join(probes))
        data = c.transient(args.seconds, sample_rate=args.rate)
        n = len(next(iter(data.values()))[0])
        print("采样点:", n)
        out = c.export_csv(args.out, data)
        print("已写出:", out)
        if args.png:
            print("原理图:", c.snapshot(args.png))
    return 0


def cmd_ac(args):
    with Multisim() as ms:
        c = ms.open(args.file)
        probes = c.probes()
        if not probes:
            print("没有探针，取不到数据。")
            return 2
        data = c.ac_sweep(args.start, args.stop, args.points, SweepType.Decade)
        out = c.export_csv(args.out, data)
        print("已写出:", out)
    return 0


def cmd_img(args):
    with Multisim() as ms:
        c = ms.open(args.file)
        print(c.snapshot(args.out, ImgFmt.PNG))
    return 0


def cmd_netlist(args):
    with Multisim() as ms:
        c = ms.open(args.file)
        txt = c.netlist(True, ExportFmt.Text)
        print(txt)
        if args.out:
            open(args.out, "w", encoding="utf-8").write(txt)
    return 0


def cmd_bom(args):
    with Multisim() as ms:
        c = ms.open(args.file)
        txt = c.bom(False, ExportFmt.Text)
        print(txt)
        if args.out:
            open(args.out, "w", encoding="utf-8").write(txt)
    return 0


def cmd_demo(args):
    import demo
    return demo.main()


def main(argv=None):
    p = argparse.ArgumentParser(prog="run.bat", description="操控 NI Multisim 14.3")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("selftest", help="自检：能否连上 Multisim").set_defaults(fn=cmd_selftest)

    s = sub.add_parser("info", help="看电路里有什么")
    s.add_argument("file")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("sim", help="跑瞬态仿真并导出 CSV")
    s.add_argument("file")
    s.add_argument("--seconds", type=float, default=0.02)
    s.add_argument("--rate", type=float, default=10000.0)
    s.add_argument("--out", default=os.path.join("out", "transient.csv"))
    s.add_argument("--png", default=None)
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("ac", help="交流扫频")
    s.add_argument("file")
    s.add_argument("--start", type=float, default=10.0)
    s.add_argument("--stop", type=float, default=1e6)
    s.add_argument("--points", type=int, default=100)
    s.add_argument("--out", default=os.path.join("out", "ac.csv"))
    s.set_defaults(fn=cmd_ac)

    s = sub.add_parser("img", help="导出原理图图片")
    s.add_argument("file")
    s.add_argument("--out", default=os.path.join("out", "circuit.png"))
    s.set_defaults(fn=cmd_img)

    s = sub.add_parser("netlist", help="导出网表")
    s.add_argument("file")
    s.add_argument("--out", default=None)
    s.set_defaults(fn=cmd_netlist)

    s = sub.add_parser("bom", help="导出 BOM")
    s.add_argument("file")
    s.add_argument("--out", default=None)
    s.set_defaults(fn=cmd_bom)

    sub.add_parser("demo", help="端到端演示（生成 CSV/图片/HTML 报告）").set_defaults(fn=cmd_demo)

    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        p.print_help()
        return 1
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
