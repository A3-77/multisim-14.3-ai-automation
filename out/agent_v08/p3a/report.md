# RC 低通滤波器 2 kHz 增益/相位 实测报告

- 会话：`c-7ee828f13d`（`rc_lpf_1k_100n_2k`）
- 仿真：`s-6f3a22498e`（transient，stop=3 ms，sample_rate=200 kHz，n=600，6 个周期）
- 工具调用总数：14 次；报错 1 次

## 1. 电路与参数

| 位号 | family / part | 值 | 说明 |
|---|---|---|---|
| V1 | SIGNAL_VOLTAGE_SOURCES / AC_VOLTAGE | 1 V（amplitude），parameters.frequency = 2000 Hz | 正弦激励 |
| R1 | RESISTOR / RESISTOR_VIRTUAL | 1000 Ω | 串联电阻 |
| C1 | CAPACITOR / CAPACITOR_VIRTUAL | 1e-7 F（100 nF） | 输出节点对地 |
| GND1 | POWER_SOURCES / GROUND | — | 参考地 |

连接（3 条网络）：

- `0`（地）：V1.− , C1.2 , GND1.1
- `in`：V1.+ , R1.1
- `n1`（输出）：R1.2 , C1.1

探针：`out` → 网络 `n1`，`in` → 网络 `in`（两个都是电压探针）。

后端拓扑判定：`kind = divider`（get_circuit 时）/ `bypass`（simulate 返回，n_series=1、n_shunt=1、out_net=n1），`supported = true`。
Multisim 回读的元件值：R1 = 1000.0 Ω，C1 = 1e-07 F（与设定一致）。

## 2. 实际值（来自工具返回）

`measure(what="all")` 的单通道结果（`amp` 为正弦拟合幅值，`phase_deg` 相对源）：

| 通道 | probe_id | net | amp (V) | phase_deg | rms | mean |
|---|---|---|---|---|---|---|
| 输出 | `out` | n1 | 0.619463867 | −51.578274 | 0.442264700 | 0.016638707 |
| 输入 | `in` | in | 0.996793695 | −0.000249 | 0.704838327 | 0.000001875 |

由两个通道的幅值/相位取比值，得到实际传递函数：

- **实际增益 = 0.619463867 / 0.996793695 = 0.621456**（−4.131 dB）
- **实际相位 = −51.578274 − (−0.000249) = −51.578°**（滞后）
- **实际输出幅值 = 0.619464 V**（输入幅值实测 0.996794 V，源设定 1 V）

> 关于工具聚合字段的一个观察（不是报错）：`measure` 的 ratio 模式返回
> `"mode":"ratio", "in_probe":"out", "out_probe":"in", "gain":1.6091232225725118, "phase_deg":51.57802477458959`。
> 它把两个探针的输入/输出角色判反了，所以聚合 `gain` 正好是 1/0.621456，`phase_deg` 是正号。
> 单通道 `amp` / `phase_deg` 是正确的，本报告的增益/相位由上表两个通道的实测值相除/相减得到，未采用该聚合值。

`simulate` 返回的 summary（含启动暂态，故 max/min 略不对称）：out max=0.690090、min=−0.620132；in max=0.997097、min=−0.997097。
波形 CSV（工具返回的 artifact `.../sims/s-6f3a22498e.csv`）独立最小二乘复核（跳过第 1 个周期）：out amp=0.619449、相位相对输入 −51.56°，in amp=0.996790 —— 与 `measure` 一致（幅值差 1.5e-5 V）。

## 3. 理论值（自算，纯标准库）

R = 1000 Ω，C = 100 nF，f = 2000 Hz，Vs = 1 V（幅值）

- ωRC = 2π·2000·1000·100e−9 = **1.256637**
- 截止频率 fc = 1/(2πRC) = **1591.5494 Hz**
- H = 1/(1+jωRC) → |H| = 1/√(1+1.256637²) = **0.622677**
- ∠H = −arctan(1.256637) = **−51.4881°**
- 输出幅值 = 1 V × 0.622677 = **0.622677 V**

工具返回的 `theory` 块与自算完全一致（gain=0.6226769922994999，phase_deg=−51.48811274603342，fc=1591.5494309189537），可作为交叉验证。

## 4. 误差

| 量 | 实际 | 理论 | 绝对误差 | 相对误差 |
|---|---|---|---|---|
| 增益 | 0.621456 | 0.622677 | −0.001221 | **−0.196 %** |
| 相位 | −51.578° | −51.488° | −0.0899° | −0.175 % |
| 输出幅值 | 0.619464 V | 0.622677 V | −0.003213 V | **−0.516 %** |

误差量级符合数值仿真的预期（采样 100 点/周期、正弦拟合 + 有限精度读数），电路行为与一阶 RC 低通理论一致。

## 5. 报错记录（全文）

只有 1 次报错，发生在第 2 次调用。

**第 2 次调用** `add_component`（加 AC_VOLTAGE，我把频率写成了顶层便捷字段 `frequency`）：

```json
{
  "ok": false,
  "error": {
    "code": "MISSING_PARAMETER",
    "message": "AC_VOLTAGE 需要 frequency（单位 Hz）",
    "hint": "add_component 里传 parameters={'frequency': <数值>}。",
    "context": {
      "part": "AC_VOLTAGE",
      "field": "frequency",
      "supported": ["frequency"]
    }
  }
}
```

- 依据字段：`hint`（配合 `context.field = "frequency"`、`context.supported = ["frequency"]`）。
- 改法：把 `"frequency": 2000` 改为 `"parameters": {"frequency": 2000}`，其余参数不动。
- 重试结果：第 4 次调用成功，返回的 component 里 `value_name="amplitude"`、`value_unit="V"`、`parameters={"frequency": 2000.0}`，`pins=["1","2"]`、`aliases={"+" :"1","-":"2"}`。
- 之后没有再出现同类错误（频率参数此后一直用 `parameters` 传递）。

另外两处属于正常状态而非报错，按提示推进即可：`create_circuit` 后 `topology.supported=false, reason=NO_SOURCE`（还没加电源）；加完源后 `reason=NO_GROUND`（还没接地），补上 GND1 后 `supported=true`。

## 6. 调用统计

| # | 调用 | 结果 |
|---|---|---|
| 1 | `tools` | ok（发现 8 个工具） |
| 2 | `add_component` (AC_VOLTAGE, 顶层 frequency) | **ERR: MISSING_PARAMETER** |
| 3 | `add_component` (R1 1000 Ω) | ok |
| 4 | `add_component` (AC_VOLTAGE, parameters.frequency=2000) | ok |
| 5 | `add_component` (C1 1e-7 F) | ok |
| 6 | `add_component` (GND1) | ok |
| 7 | `get_circuit` | ok（确认 GND1 引脚名 = "1"） |
| 8 | `connect` (V1.−, C1.2, GND1.1) | ok |
| 9 | `connect` (V1.+, R1.1) | ok |
| 10 | `connect` (R1.2, C1.1) | ok（topology=divider, supported=true） |
| 11 | `add_probe` (out → n1) | ok |
| 12 | `add_probe` (in → in) | ok |
| 13 | `simulate` (transient) | ok（compile 17.1 s，run 4.2 s，总 21.3 s） |
| 14 | `measure` (all) | ok |

- 总调用：**14 次**（其中 `tools` 1 次、schema 0 次、业务调用 13 次）
- 报错：**1 次**（MISSING_PARAMETER，第 2 次调用）
- 是否"同样的错犯两次"：**没有**。频率参数的错误只出现一次，修正后未复现；其余调用全部一次成功。
- 没有使用 `schema` 子命令，因为 `tools` 返回的 inputSchema 已足够完整（`add_probe` 的 target 写法、`connect` 的引脚写法、`measure` 的 probe_id 语义都在其中）。
