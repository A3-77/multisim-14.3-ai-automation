# -*- coding: utf-8 -*-
"""
msc.py —— 用 Python 操控 NI Multisim 14.3

底层走 NI 官方的 Multisim Automation API（COM 组件 MultisimInterface.MultisimApp，
实现在 MSInterface.dll）。同一套接口 NI 自己给 LabVIEW 用，所以稳定、有官方文档。

硬性前提：
  * 必须是 **32 位** Python。该 COM 类只注册在注册表的 WOW6432Node（32 位视图）下，
    64 位进程调用会得到「没有注册类 / Class not registered」。
  * 本目录自带的 runtime\\py32 就是 32 位 Python 3.11，直接用 run.bat 即可。

基本用法：
    from msc import Multisim
    with Multisim() as ms:
        c = ms.open(r"D:\\circuit.ms14")
        print(c.components())      # ('R1','C1','U1',...)
        print(c.probes())          # ('V(Probe1)', ...)  <- 电路里放的探针
        data = c.transient(0.02, sample_rate=10000)
        c.export_csv("out/run.csv", data)
        c.snapshot("out/circuit.png")
"""

import os
import sys
import time
import csv

import pythoncom
from win32com.client import Dispatch, VARIANT

PROGID = "MultisimInterface.MultisimApp"

# ---------------------------------------------------------------- 枚举常量
# 数值取自 MSInterface.dll 的类型库，和官方文档一致。
class SimState:
    Stopped, Running, Paused = 0, 1, 2


class IOType:
    All, Voltage, Current, Power, Digital = 0, 1, 2, 3, 4


class SweepType:
    Decade, Octave, Linear = 0, 1, 2


class Interp:
    Raw, ForceStep, Linear, Spline, Coerce = 0, 1, 2, 3, 4


class CompType:
    All, AllRLC, Resistor, Capacitor, Inductor = 0, 1, 2, 3, 4


class ImgFmt:
    PNG, JPG, BMP = 0, 1, 2


class ExportFmt:
    Text, CSV = 0, 1


class ParamLevel:
    All, TopLevel = 0, 1


STATE_NAME = {0: "stopped", 1: "running", 2: "paused"}


def _bstr_array(seq):
    """把 Python 序列变成 COM 需要的 SAFEARRAY<BSTR>（VARIANT 包装）。

    这个接口的数组参数声明成 VARIANT，但服务器只认 VT_ARRAY|VT_BSTR；
    直接传 tuple 会变成 VT_ARRAY|VT_VARIANT，报「expected array of type string」。
    """
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, tuple(seq))


def _prop_put(obj, name, value, *args):
    """带参数的 propput（例如 RLCValue(name) = value），pywin32 没法用属性语法写。"""
    disp = obj._oleobj_.GetIDsOfNames(name)
    return obj._oleobj_.Invoke(disp, 0, pythoncom.DISPATCH_PROPERTYPUT, 0, *(tuple(args) + (value,)))


def _prop_get(obj, name, *args):
    disp = obj._oleobj_.GetIDsOfNames(name)
    return obj._oleobj_.Invoke(disp, 0, pythoncom.DISPATCH_PROPERTYGET, 1, *args)


def _fix(text):
    """Multisim 返回的 BSTR 里中文是 UTF-8 字节被当成 latin-1 解出来的，倒回去。"""
    if not text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except Exception:
        return text


# ---------------------------------------------------------------- 应用对象
class Multisim:
    """Multisim 应用实例。

    Connect() 会**新启动**一个 Multisim 进程（不是你手动开的那个）。
    Disconnect() 会把它关掉。所以脚本跑完 Multisim 就没了，别指望在里面留东西。
    """

    def __init__(self, connect=True):
        self._app = Dispatch(PROGID)
        self._circuits = []
        if connect:
            self.connect()

    # -- 生命周期 -------------------------------------------------
    def connect(self):
        self._app.Connect()
        return self

    def disconnect(self):
        try:
            self._app.Disconnect()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.disconnect()

    # -- 属性 -----------------------------------------------------
    @property
    def version(self):
        return self._app.VersionInfo

    @property
    def exe_path(self):
        return self._app.Path

    @property
    def connected(self):
        return bool(self._app.IsConnected)

    @property
    def last_error(self):
        return _fix(self._app.LastErrorMessage)

    def set_log_file(self, path):
        self._app.LogFile = os.path.abspath(path)

    # -- 打开 / 新建 ----------------------------------------------
    def open(self, path):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        c = Circuit(self, self._app.OpenFile(path))
        self._circuits.append(c)
        return c

    def new(self):
        c = Circuit(self, self._app.NewFile())
        self._circuits.append(c)
        return c


# ---------------------------------------------------------------- 电路对象
class Circuit:
    """一个打开的电路。所有方法都是同步调用，失败时抛 RuntimeError 并带上 Multisim 的错误原文。"""

    def __init__(self, app, com_obj):
        self._app = app
        self._c = com_obj

    # -- 基本信息 -------------------------------------------------
    @property
    def name(self):
        return self._c.CircuitName

    @property
    def file(self):
        return self._c.FileName

    @property
    def state(self):
        return self._c.SimulationState

    @property
    def state_name(self):
        return STATE_NAME.get(self.state, str(self.state))

    @property
    def last_error(self):
        return _fix(self._c.LastErrorMessage)

    def _err(self, what):
        msg = self.last_error or "（Multisim 没给出原因）"
        raise RuntimeError("%s 失败：%s" % (what, msg))

    def __repr__(self):
        return "<Circuit %r file=%r>" % (self.name, os.path.basename(self.file or ""))

    # -- 元器件 ---------------------------------------------------
    def components(self, kind=CompType.All):
        """返回元件位号元组，如 ('R1','C1','U1')。"""
        return tuple(self._c.EnumComponents(kind) or ())

    def sections(self, comp):
        """元件可替换的 section（子型号/封装）列表。"""
        return tuple(self._c.EnumSections(comp) or ())

    def rlc(self, comp):
        """读 R/L/C 的值（基本单位：Ω / H / F）。非 RLC 元件会抛错。"""
        return self._c.RLCValue(comp)

    def set_rlc(self, comp, value):
        """改 R/L/C 的值。这是唯一能"改电路"的入口。"""
        _prop_put(self._c, "RLCValue", float(value), comp)

    def replace_component(self, comp, section, source_database, source_group,
                          source_family, source_name, model_name=""):
        """换元件（换成库里另一个器件），返回新位号。"""
        return self._c.ReplaceComponent(comp, section, source_database, source_group,
                                        source_family, source_name, model_name)

    # -- 电路参数（.param / 全局参数）-----------------------------
    def params(self, level=ParamLevel.TopLevel):
        return tuple(self._c.EnumCircuitParameters(level) or ())

    def param(self, name):
        return self._c.CircuitParameterValue(name)

    def set_param(self, name, value):
        _prop_put(self._c, "CircuitParameterValue", float(value), name)

    # -- 变体 -----------------------------------------------------
    def variants(self):
        return tuple(self._c.EnumVariants() or ())

    @property
    def active_variant(self):
        return self._c.ActiveVariant

    @active_variant.setter
    def active_variant(self, name):
        self._c.ActiveVariant = name

    # -- 探针 = 仿真输出 ------------------------------------------
    def probes(self, kind=IOType.All):
        """枚举电路里的探针。**没有探针就没有输出，也就没法取数据。**

        Multisim 里放探针：Simulate 工具栏上的「探针」按钮，或者
        Place » Probe，点一下要测的节点。探针会自动命名 Probe1、Probe2…
        """
        return tuple(self._c.EnumOutputs(kind) or ())

    def inputs(self, kind=IOType.All):
        return tuple(self._c.EnumInputs(kind) or ())

    # -- 仿真控制 -------------------------------------------------
    def run(self, seconds=1.0, pause=False):
        """跑仿真。注意：**非阻塞**，立刻返回，之后用 wait() 取数据。"""
        self._c.RunSimulation(float(seconds), bool(pause))

    def run_until_next_output(self):
        self._c.RunSimulationUntilNextOutput()

    def stop(self):
        if self.state != SimState.Stopped:
            self._c.StopSimulation()

    def pause(self):
        if self.state == SimState.Running:
            self._c.PauseSimulation()

    def resume(self):
        if self.state == SimState.Paused:
            self._c.ResumeSimulation()

    def wait(self, timeout_ms=5000):
        """等下一个输出点。返回 (有数据的输出名元组, 是否超时)。"""
        names, timed_out = self._c.WaitForNextOutput(int(timeout_ms))
        return tuple(names or ()), bool(timed_out)

    def request_output(self, name, sample_rate=10000.0, num_samples=1000,
                       method=Interp.Raw, repeat=False):
        self._c.SetOutputRequest(name, int(method), float(sample_rate),
                                 int(num_samples), bool(repeat))

    def clear_output(self, name):
        self._c.ClearOutputRequest(name)

    def read(self, name):
        """读某个探针的数据，返回 (时间列表, 数值列表)。数据是累计的，取最新一次即可。"""
        arr, method = self._c.GetOutputData(name)
        return list(arr[0]), list(arr[1])

    def read_all(self, outputs):
        return {nm: self.read(nm) for nm in outputs}

    # -- 三种常用分析（封装好的一套流程）--------------------------
    def transient(self, seconds=1.0, sample_rate=10000.0, outputs=None,
                  num_samples=None, timeout_ms=15000, settle=0.3,
                  method=Interp.Linear):
        """瞬态（时域）仿真。返回 {探针名: (时间[], 数值[])}。

        内部流程：SetOutputRequest -> RunSimulation -> WaitForNextOutput -> GetOutputData
        """
        outputs = list(outputs or self.probes())
        if not outputs:
            raise RuntimeError(
                "这个电路里没有探针，取不到数据。\n"
                "在 Multisim 里放一个探针（Place » Probe，点节点），存盘后再跑。")
        n = int(num_samples or max(1000, seconds * sample_rate * 1.2))
        for nm in outputs:
            self.request_output(nm, sample_rate, n, method=method)
        self.run(seconds, pause=False)
        deadline = time.time() + timeout_ms / 1000.0
        got = ()
        while time.time() < deadline:
            got, timed_out = self.wait(600)
            if got:
                break
            if self.state == SimState.Stopped:
                break
        time.sleep(settle)
        if self.state != SimState.Stopped:
            self.stop()
        return self.read_all(outputs)

    def ac_sweep(self, start=10.0, stop=1e6, points=100, sweep=SweepType.Decade,
                 outputs=None, timeout_ms=20000):
        """交流扫频（幅频/相频）。电路里要有 AC 源，否则数值会全是 0。"""
        outputs = list(outputs or self.probes())
        if not outputs:
            raise RuntimeError("这个电路里没有探针，取不到数据。")
        self._c.DoACSweep(int(sweep), int(points), float(start), float(stop),
                          _bstr_array(outputs))
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            got, timed_out = self.wait(800)
            if got:
                break
            if self.state == SimState.Stopped:
                break
        time.sleep(0.3)
        if self.state != SimState.Stopped:
            self.stop()
        return self.read_all(outputs)

    def ac_single(self, freq=1000.0, outputs=None):
        """单频交流分析。"""
        outputs = list(outputs or self.probes())
        self._c.DoACSingleFrequency(float(freq), _bstr_array(outputs))
        self.wait(3000)
        return self.read_all(outputs)

    def dc_op(self, outputs=None):
        """直流工作点。注意：部分电路（比如纯稳压电源）会直接报「未指定的错误」。"""
        outputs = list(outputs or self.probes())
        try:
            self._c.DoDCOperatingPoint(_bstr_array(outputs))
        except Exception:
            self._err("直流工作点分析")
        self.wait(3000)
        return self.read_all(outputs)

    # -- 导出 -----------------------------------------------------
    def snapshot(self, path, fmt=ImgFmt.PNG):
        """把原理图存成图片。"""
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return self._c.GetCircuitImage(int(fmt), path)

    def netlist(self, with_probes=False, fmt=ExportFmt.Text, path=None):
        """导出网表（文本或 CSV）。返回网表字符串。"""
        arg = path if path else None
        return _fix(self._c.ReportNetlist(bool(with_probes), int(fmt), arg))

    def bom(self, real_only=False, fmt=ExportFmt.Text, path=None):
        """导出 BOM（元件清单）。"""
        arg = path if path else None
        return _fix(self._c.ReportBOM(bool(real_only), int(fmt), arg))

    def save(self):
        return self._c.Save()

    def save_as(self, path):
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return self._c.SaveAs(path)

    @staticmethod
    def export_csv(path, data):
        """把 read_all()/transient() 的结果写成 CSV（多探针按时间对齐）。"""
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        names = list(data)
        if not names:
            raise ValueError("没有数据可写")
        base = names[0]
        t = data[base][0]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["time_s"] + names)
            for i in range(len(t)):
                row = [t[i]]
                for nm in names:
                    v = data[nm][1]
                    row.append(v[i] if i < len(v) else "")
                w.writerow(row)
        return path


# ---------------------------------------------------------------- 自检
def selftest():
    """连上 Multisim，把能力清单打一遍。不打开任何电路。"""
    print("=" * 60)
    print("Multisim 自动化自检")
    print("=" * 60)
    import struct
    print("Python : %s (%d-bit)" % (sys.version.split()[0], struct.calcsize("P") * 8))
    with Multisim() as ms:
        print("版本   :", ms.version)
        print("路径   :", ms.exe_path)
        print("已连接 :", ms.connected)
        c = ms.new()
        print("新建电路:", c.name)
        print("探针数 :", len(c.probes()))
        print("元件数 :", len(c.components()))
        print()
        print("结论：COM 通道正常，可以操控。")
    print("=" * 60)


if __name__ == "__main__":
    selftest()
