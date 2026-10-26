# -*- coding: utf-8 -*-
"""P0 验收仿真：在自建电路上跑一次真实仿真，确认 Multisim 实际读到的 R1 是 1kΩ。

流程：
    1. 用 32 位 Python 连上 Multisim（COM API，见 msc.py）
    2. 打开 out/ref/with_probes.ms14（只读，不保存）
    3. 分别用 IOType.All / Voltage / Current 枚举可用 output
    4. 对每个 output 跑直流工作点；dc_op 报错就退回 transient(0.2s) 取稳态末值
    5. 导出网表，提取 R1 / V1 的网表行
    6. 写 out/p0_validation.json

约束：不修改 out/ref/ 下任何文件（不调用 save/save_as）。
"""
import json
import os
import struct
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import msc  # noqa: E402

CIRCUIT = os.path.join(ROOT, "out", "ref", "with_probes.ms14")
OUT_DIR = os.path.join(ROOT, "out")
JSON_PATH = os.path.join(OUT_DIR, "p0_validation.json")
NETLIST_PATH = os.path.join(OUT_DIR, "p0_netlist.txt")


def hr(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def export_netlist(c, path):
    """导出网表。优先让 Multisim 直接写文件，失败则用返回值自己写。"""
    txt = None
    try:
        txt = c.netlist(with_probes=True, fmt=msc.ExportFmt.Text, path=path)
    except Exception as e:
        print("  ReportNetlist(path=...) 失败：%r，改用返回值写文件" % (e,))
        txt = c.netlist(with_probes=True, fmt=msc.ExportFmt.Text, path=None)
    if not txt:
        raise RuntimeError("网表导出返回空")
    # Multisim 自己写了就用它的，否则用返回值
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def find_netlist_line(lines, refdes):
    """网表里以 refdes 作为第一个 token 的行（忽略大小写）。"""
    import re
    pat = re.compile(r"^\s*" + re.escape(refdes) + r"\b", re.IGNORECASE)
    for ln in lines:
        if pat.match(ln):
            return ln.rstrip()
    return None


def last_value(data, name):
    """data = {name: (t[], v[])}，取该探针的最后一个数值。"""
    if name not in data:
        return None
    t, v = data[name]
    if not v:
        return None
    return float(v[-1])


def main():
    result = {
        "circuit": os.path.relpath(CIRCUIT, ROOT),
        "python_bits": struct.calcsize("P") * 8,
        "python_version": sys.version.split()[0],
        "multisim_version": None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "outputs_all": [],
        "outputs_voltage": [],
        "outputs_current": [],
        "dc_values": {},
        "dc_errors": {},
        "transient_final": {},
        "transient_errors": {},
        "netlist_path": os.path.relpath(NETLIST_PATH, ROOT),
        "netlist_r1_line": None,
        "netlist_v1_line": None,
        "netlist_full": None,
        "rlc_r1": None,
        "components": [],
        "errors": [],
    }

    hr("P0 验收仿真 —— 确认 Multisim 读到的 R1 是 1kΩ")
    print("Python      : %s (%d-bit)" % (result["python_version"], result["python_bits"]))
    print("电路文件    : %s" % CIRCUIT)
    print("文件大小    : %d 字节" % os.path.getsize(CIRCUIT))

    with msc.Multisim() as ms:
        result["multisim_version"] = ms.version
        print("Multisim    : %s" % ms.version)
        print("已连接      : %s" % ms.connected)

        c = ms.open(CIRCUIT)
        print("打开电路    : %s" % c)
        print("仿真状态    : %s" % c.state_name)

        # ---- 3. 枚举 output（三种 IOType）---------------------------
        hr("步骤 3：枚举可用 output")
        for label, kind in (("All", msc.IOType.All),
                            ("Voltage", msc.IOType.Voltage),
                            ("Current", msc.IOType.Current)):
            try:
                names = list(c.probes(kind))
            except Exception as e:
                names = []
                result["errors"].append("EnumOutputs(%s) 失败：%r" % (label, e))
            key = {"All": "outputs_all", "Voltage": "outputs_voltage",
                   "Current": "outputs_current"}[label]
            result[key] = names
            print("  IOType.%-8s -> %d 个：%s" % (label, len(names), names))

        outputs = result["outputs_all"] or result["outputs_voltage"]
        if not outputs:
            print("\n ！没有可用 output，无法取数。")
        print("  c.probes()（默认 All）-> %s" % (list(c.probes()),))

        # ---- 附带：直接读元件值 -------------------------------------
        hr("附带：COM 直接读元件值")
        try:
            comps = list(c.components())
            result["components"] = comps
            print("  元件位号    : %s" % comps)
            for ref in ("R1", "V1"):
                if ref in comps:
                    try:
                        v = c.rlc(ref)
                        result["rlc_r1" if ref == "R1" else "rlc_v1"] = v
                        print("  RLCValue(%s) = %r" % (ref, v))
                    except Exception as e:
                        print("  RLCValue(%s) 失败：%r" % (ref, e))
                        result["errors"].append("RLCValue(%s)：%r" % (ref, e))
        except Exception as e:
            print("  EnumComponents 失败：%r" % (e,))
            result["errors"].append("EnumComponents：%r" % (e,))

        # ---- 4. 对每个 output 跑 dc_op，失败退回 transient ----------
        for nm in outputs:
            hr("步骤 4：output %r —— 直流工作点" % nm)
            try:
                data = c.dc_op([nm])
                val = last_value(data, nm)
                if val is None:
                    raise RuntimeError("dc_op 返回空数据")
                result["dc_values"][nm] = val
                t, v = data[nm]
                print("  dc_op 成功，采样点 %d 个，末值 = %.6g" % (len(v), val))
                continue
            except Exception as e:
                msg = "%s" % (e,)
                result["dc_errors"][nm] = msg
                result["errors"].append("dc_op(%s)：%s" % (nm, msg))
                print("  dc_op 失败：%s" % msg)
                print("  -> 退回 transient(0.2s) 取稳态末值")

            hr("步骤 4（回退）：output %r —— transient 0.2s" % nm)
            try:
                data = c.transient(0.2, outputs=[nm])
                val = last_value(data, nm)
                if val is None:
                    raise RuntimeError("transient 返回空数据")
                result["transient_final"][nm] = val
                t, v = data[nm]
                print("  transient 成功，采样点 %d 个" % len(v))
                print("  末值 = %.6g   首值 = %.6g" % (v[-1], v[0]))
            except Exception as e:
                msg = "%s" % (e,)
                result["transient_errors"][nm] = msg
                result["errors"].append("transient(%s)：%s" % (nm, msg))
                print("  transient 也失败：%s" % msg)
                traceback.print_exc()

        # ---- 5. 导出网表 -------------------------------------------
        hr("步骤 5：导出网表")
        try:
            text = export_netlist(c, NETLIST_PATH)
            lines = text.splitlines()
            result["netlist_r1_line"] = find_netlist_line(lines, "R1")
            result["netlist_v1_line"] = find_netlist_line(lines, "V1")
            print("  网表已写入 %s（%d 行，%d 字符）"
                  % (NETLIST_PATH, len(lines), len(text)))
            print("  R1 行 : %r" % result["netlist_r1_line"])
            print("  V1 行 : %r" % result["netlist_v1_line"])
            if result["netlist_r1_line"] is None or result["netlist_v1_line"] is None:
                print("  ！没找到 R1/V1 行，网表全文如下：")
                for ln in lines:
                    print("    | " + ln)
        except Exception as e:
            result["errors"].append("导出网表：%r" % (e,))
            print("  导出网表失败：%r" % (e,))
            traceback.print_exc()

    # ---- 6. 写 JSON -----------------------------------------------
    hr("步骤 6：写 out/p0_validation.json")
    result["netlist_full"] = (result["netlist_r1_line"], result["netlist_v1_line"])
    del result["netlist_full"]
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("  已写入 %s" % JSON_PATH)

    # ---- 结论 -------------------------------------------------------
    hr("结论")
    print("  探针 output : %s" % result["outputs_all"])
    if result["dc_values"]:
        print("  dc_op 读数  : %s" % result["dc_values"])
    if result["transient_final"]:
        print("  transient   : %s" % result["transient_final"])
    print("  网表 R1     : %s" % result["netlist_r1_line"])
    print("  网表 V1     : %s" % result["netlist_v1_line"])
    if result["errors"]:
        print("  过程中的错误 :")
        for e in result["errors"]:
            print("    - %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
