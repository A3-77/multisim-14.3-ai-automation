# P0 验收通过 —— 从空白 .ms14 生成可仿真的真实电路

> 日期：2026-10-24
> 环境：Multisim 14.3（本机）、32 位 Python 3.11（`runtime/py32`）、COM `MultisimInterface.MultisimApp`

## 结论

从空白电路出发，用纯代码生成：

```
V1 = 5V 直流源
R1 = 1kΩ
C1 = 1pF      （只为让交互仿真有动态过程，直流下等效开路）
GND
电压探针 V(探针1)（新式 ProbeExt，落在导线顶点）
```

Multisim 能正常打开并**真实仿真**，通过 COM 读到：

| 项 | 值 |
| --- | --- |
| `EnumOutputs()` | `V(探针1)` |
| 采样点 | 100 |
| 电压 min / max / last | **5.0 V / 5.0 V / 5.0 V** |
| `RLCValue('R1')` | **1000.0 Ω** |
| 仿真状态序列 | stopped → **running** → stopped |
| 结论 | V=5V、R=1kΩ → **I = 5mA** |

## 根因（本轮最关键发现）

`msbuild.Assembler.add()` 深拷贝元件符号时，漏掉了 **`CIITPinSymbolComp@PortID`** 的重映射：

```
原元件：  引脚符号 PortID -> 本电路 CiPort CiID        ✅
克隆元件：引脚符号 PortID -> donor 的旧 CiPort CiID    ❌（目标文件里不存在）
```

结果：元件、参数、导线看起来全对，但**引脚符号与电气端口脱钩**，Multisim 建不出网表 →
`RunSimulation` 秒停、`GetOutputData` 报「输出未找到」、`RLCValue` 报「未指定的错误」。

修复：在克隆符号时，按引脚名把 `PortID` 重映射到新的 CiPort CiID（见 `tools/msbuild.py`）。

这个 bug 会同时影响所有克隆出来的元件，是「自动化生成」从“看起来对”到“真的能跑”的分水岭。

## 复现

```powershell
cd multisim-ctrl
python tools\build_acceptance.py                  # 生成 out/ref/acceptance.ms14
runtime\py32\python.exe tools\p11_run.py out\ref\acceptance.ms14   # 打开 + 瞬态 + 导出
```

或直接用 COM 读：

```python
import msc
ms = msc.Multisim()
c = ms.open(r"out\ref\acceptance.ms14")
print(c.probes())          # ('V(探针1)',)
print(c.rlc("R1"))         # 1000.0
d = c.transient(0.01)
print(d["V(探针1)"][1][:3])  # [5.0, 5.0, 5.0]
```

## 产物

| 文件 | 说明 |
| --- | --- |
| `out/ref/acceptance.ms14` | 验收电路（29208 字节，可打开、可仿真） |
| `out/ref/p0_waveform.csv` | 100 点波形，恒 5.0V |
| `out/ref/p11_final.json` | 本轮验证记录（outputs / V 统计 / R1 / ever_running / pass） |
| `out/ref/acceptance.noprobe.ms14` | 对照：无探针版本 |

## 仍然成立的规律（后续会用到）

1. **纯直流电路（只有 R + 源）不会进入 running** —— 交互仿真没有可积分的时变过程，属正常；要取数要么用 DC 工作点，要么加一个极小电容走瞬态。
2. **探针位置必须精确落在导线顶点**（不是线段中间、不是引脚端点），否则不会注册成 output。
3. **老式探针（CiProbeComp）需要真实 CIITLinkComp 导线接入网络**；新式 ProbeExt 靠几何位置绑定，但同样要在顶点上。
4. COM 不稳定：一次分析失败后可能 segfault；**一个文件一个进程**、跑前 `taskkill /F /IM multisim.exe`。

## 下一步

- P1：统一 `add_part(family, part, ...)`，作为 Circuit IR 的底座；
- P1.5：RC 低通滤波器（多节点 + 瞬态波形）；
- P2：108 个样例的元件覆盖率；
- P3：Circuit IR + 自然语言 → 电路。
