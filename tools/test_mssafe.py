# -*- coding: utf-8 -*-
"""回归测试：守住「XML 往返必须无损」这个不变量。

这是整个项目最关键的一条约束。历史上因为 ElementTree 把
`CIITDiagram@SimState` 属性里的换行归一化成空格，仿真配置被压平，
导致电阻电流恒为 0，被误判成「克隆的电阻是开路的」，为此浪费了
大量时间去做结构考古（NodeText / junction / ComponentPort / PortID…），
全都是白费。

本测试不需要 Multisim，秒级完成：
  1. mssafe 往返后换行数必须与原文一致
  2. 归一化「声明 + 自闭合标签空格」后，往返结果必须与原文逐字节相同
  3. SimState 里的 SIMULATION_INFO 必须原样保留

用法：
    runtime\\py32\\python.exe tools/test_mssafe.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl
import mssafe

SAMPLES = [
    os.path.join(ROOT, "corpus", "samples14",
                 "Amplificador para resistencia de 1mOhm.ms14"),
    os.path.join(ROOT, "corpus", "samples14", "buck.ms14"),
    os.path.join(ROOT, "corpus", "samples14", "nivel de agua con 555.ms14"),
    os.path.join(ROOT, "corpus", "samples14", "05 滤波器.ms14"),
]


def norm(b):
    """抹掉两处已知无害的序列化差异：
    - XML 声明：ET 写单引号 + 小写 encoding，我们统一还原成原样（所以这里也去掉）
    - 自闭合标签：ET 写 `<Item />`，Multisim 写 `<Item/>`
    """
    s = b.decode("latin-1")
    s = re.sub(r"<\?xml[^>]*\?>", "", s)
    s = re.sub(r"\s*/>", "/>", s)
    return s


def check(path):
    name = os.path.basename(path)
    raw, info = dcl.read_ms14(path)
    out = mssafe.roundtrip(raw)

    n_orig = raw.count(b"\n")
    n_out = out.count(b"\n")
    ok_nl = (n_orig == n_out)

    ok_same = (norm(raw) == norm(out))
    first = None
    if not ok_same:
        a, b = norm(raw), norm(out)
        for i in range(min(len(a), len(b))):
            if a[i] != b[i]:
                first = i
                break

    ok_sim = (b"SIMULATION_INFO" in raw) == (b"SIMULATION_INFO" in out)

    ok = ok_nl and ok_same and ok_sim
    print("%-46s 换行 %5d→%5d %s  逐字节 %s  SimState %s  => %s"
          % (name[:46], n_orig, n_out, "OK" if ok_nl else "LOSS",
             "OK" if ok_same else "DIFF@%s" % first,
             "OK" if ok_sim else "LOSS",
             "PASS" if ok else "FAIL"))
    if not ok_same and first is not None:
        a, b = norm(raw), norm(out)
        print("      原: %r" % a[max(0, first - 60):first + 80])
        print("      新: %r" % b[max(0, first - 60):first + 80])
    return ok


def main():
    print("=" * 78)
    print("mssafe 无损往返回归测试")
    print("=" * 78)
    results = []
    for p in SAMPLES:
        if not os.path.exists(p):
            print("%-46s 跳过（文件不存在）" % os.path.basename(p)[:46])
            continue
        results.append(check(p))
    print("-" * 78)
    ok = all(results) and results
    print("总计 %d 个样本，%d 通过 => %s"
          % (len(results), sum(1 for r in results if r), "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
