# 一阶 RC 低通滤波器 —— 瞬态仿真验收报告

- 验收对象：Multisim 电路执行器（仅通过 MCP 命令行接口交互）
- 工作目录：`out/agent_v08/p3b`
- 电路名 / circuit_id：`rc_lowpass_1k_100n` / `c-0a8bdb9b95`

---

## 1. 电路与参数

| 位号 | 家族 / 型号 | 值 | 说明 |
|---|---|---|---|
| V1 | SIGNAL_VOLTAGE_SOURCES / AC_VOLTAGE | `value = 1.0`，`value_name = "amplitude"`，`value_unit = "V"`，`parameters = {"frequency": 1000.0}` | 正弦源，幅值 1 V、1 kHz |
| R1 | RESISTOR / RESISTOR_VIRTUAL | `1000.0 Ω` | 串联电阻 |
| C1 | CAPACITOR / CAPACITOR_VIRTUAL | `1e-07 F` | 对地电容 |
| GND1 | POWER_SOURCES / GROUND | — | 参考地 |

网络（`connect` 返回值）：

- `0`：`V1.2`, `GND1.1`, `C1.2`
- `in`：`V1.1`, `R1.1`
- `out`：`R1.2`, `C1.1`  ← 输出节点

探针（`add_probe` 返回值）：

| probe_id | 目标网络 | simulate 回填 label | simulate 回填 output |
|---|---|---|---|
| `P1` | `out` | `探针1` | `V(探针1)` |
| `P2` | `in` | `探针2` | `V(探针2)` |

后端拓扑判定：`kind = "bypass"`，`n_series = 1`，`n_shunt = 1`，`out_net = "out"`，`supported = true`。

Multisim 回读的元件实际值：`rlc_reported_by_multisim = {"C1": 1e-07, "R1": 1000.0}` —— 与设定值一致，因此理论计算直接用 1 kΩ / 100 nF。

### 仿真设置与实际执行

| sim_id | analysis | 请求参数 | 实际返回 | 结果 |
|---|---|---|---|---|
| `s-820fdadf29` | transient | 默认（按 1 kHz 自动推算 6 周期 / 200 点每周期） | `start=0`，`stop=0.006`，`sample_rate=200000`，`n=1200` | ok，`total_s = 19.47`（compile 15.2 / run 4.26） |
| `s-7116e2f2de` | transient | `start=0.003, stop=0.007, sample_rate=200000` | `stop=0.007`，`sample_rate=200000`，`n=1400` | ok，`total_s = 20.10` |

> 说明：第二次我传了 `start=0.003` 想跳过起振段，但返回 `n = 1400 = 0.007 × 200000`，且 CSV 第一行 `t = 0`，说明 **`start` 未生效，数据仍从 t=0 开始**。因此起振段的剔除改在分析侧完成（只取最后 2 个周期），而不是靠仿真参数。

---

## 2. 实际输出幅值 / 增益（全部来自工具返回值）

### 2.1 工具 `measure`（sim `s-7116e2f2de`，`what="all"`）

| 通道 | 网络 | `amp` (V) | `rms` (V) | `min` (V) | `max` (V) | `phase_deg` |
|---|---|---|---|---|---|---|
| P1 | out | **0.8432496814196292** | 0.5974005657701343 | -0.845410442 | 0.860876702 | -32.22518971065372 |
| P2 | in | 0.9967943822271468 | 0.7048378713944046 | -0.997667827 | 0.997667827 | -5.615422462455642e-05 |

`measure` 同时回了一个 `theory` 块（后端自己算的）：`gain = 0.8467330159648304`，`phase_deg = -32.14190763534206`，`fc = 1591.5494309189537 Hz`。我下面用自己独立算的理论值交叉核对，二者一致。

### 2.2 波形 artifact 的稳态幅值（`get_waveform` 返回的 CSV）

`get_waveform(P1)` 返回 `artifact = out\mcp\sessions\c-0a8bdb9b95\sims\s-820fdadf29.csv`；第二次仿真的 `simulate` 返回里也带 `waveform = ...\s-7116e2f2de.csv`。两者都是工具返回的 artifact 路径。我用自己的脚本（`analyze.py`，纯标准库，只读这个 CSV）对 `s-7116e2f2de.csv`（1400 点，`dt = 5e-06 s`，表头 `t,V(探针1),V(探针2)`）做逐周期 `(max-min)/2`：

| 周期 | 时间窗 | (max-min)/2 (V) |
|---|---|---|
| 1 | 0 ~ 1 ms | 0.853094（含起振，偏大） |
| 2 | 1 ~ 2 ms | 0.845411 |
| 3 | 2 ~ 3 ms | **0.845410** |
| 4 | 3 ~ 4 ms | **0.845410** |
| 5 | 4 ~ 5 ms | **0.845410** |
| 6 | 5 ~ 6 ms | **0.845410** |
| 7 | 6 ~ 7 ms | **0.845410** |

第 2 周期起即稳定在 **0.845410 V**（τ = 0.1 ms，第 2 个周期时起振项已衰减到 e⁻¹⁰ 量级）。

### 2.3 采用的实测值

| 量 | 值 | 来源 |
|---|---|---|
| 输出稳态幅值 Vout,amp | **0.845410 V** | 波形 CSV，逐周期 `(max-min)/2`（稳态） |
| 输出幅值（全窗口正弦拟合） | 0.843249 V | `measure.channels.P1.amp` |
| 输入实测幅值 Vin,amp | 0.996794 V | `measure.channels.P2.amp` |
| 实测增益（对源设定幅值 1 V） | **0.845410** | Vout,amp / 1.0 |
| 实测增益（对实测输入幅值） | 0.848133 | 0.845410 / 0.996794 |
| 实测相移 | -32.225° | `measure.channels.P1.phase_deg` |

> 关于 `measure` 顶层的 `gain` 字段：它返回 `gain = 1.1820868767468986`，并附带 `"in_probe": "P1", "out_probe": "P2"`。这是**方向搞反了**——`P1` 接的是 `out`、`P2` 接的是 `in`，它按"先建的探针是输入"来配对，于是算成了 `Vin/Vout = 1/0.8467 = 1.1811`。所以我不用这个 `gain` 字段，改用 `amp(P1)/amp(P2)` 自己算。这是本次唯一一处工具返回值需要人工复核的地方。

---

## 3. 理论输出幅值 / 增益（自己算）

标准一阶 RC 低通，输入为正弦 A₀sin(ωt)：

```
τ = R·C = 1000 × 100e-9 = 1.0e-4 s
fc = 1/(2πτ) = 1591.549 Hz
ω = 2π × 1000 = 6283.185 rad/s
ωRC = 6283.185 × 1.0e-4 = 0.628319
|H| = 1/√(1 + (ωRC)²) = 1/√(1 + 0.394785) = 0.846733
∠H = -arctan(ωRC) = -32.142°
Vout,amp = A₀·|H| = 1.0 × 0.846733 = 0.846733 V
```

| 量 | 理论值 |
|---|---|
| 截止频率 fc | 1591.55 Hz |
| 增益 \|H(jω)\| @1 kHz | **0.846733**（-1.444 dB） |
| 输出幅值 | **0.846733 V** |
| 相移 | -32.142° |

---

## 4. 误差

| 比较项 | 实测 | 理论 | 绝对误差 | 相对误差 |
|---|---|---|---|---|
| 输出幅值（稳态峰峰值法，**主结果**） | 0.845410 V | 0.846733 V | -0.001323 V | **-0.156 %** |
| 输出幅值（`measure.amp` 全窗口拟合） | 0.843249 V | 0.846733 V | -0.003484 V | -0.412 % |
| 增益（对 1 V 源设定） | 0.845410 | 0.846733 | -0.001323 | -0.156 % |
| 增益（对实测输入 0.996794 V） | 0.848133 | 0.846733 | +0.001400 | +0.165 % |
| 相移 | -32.225° | -32.142° | -0.083° | — |

**结论：输出幅值 0.8454 V，与理论 0.8467 V 相差 -0.156 %（约 1.3 mV），一阶 RC 低通的幅频特性被正确复现。**

几点必须说清楚的观察：

1. **起振段确实存在**：第 1 个周期 `(max-min)/2 = 0.853094`，比稳态高 0.9 %；`measure` 的 `amp`（0.843249）是把含起振的整段一起做正弦拟合的结果，反而比稳态低 0.26 %。两者偏差方向不同，说明"取幅值"这一步必须明确窗口，否则 0.3~0.4 % 的假误差会盖过真实精度。主结果采用稳态窗口。
2. **源本身有 -0.32 % 偏差**：`P2` 实测幅值 0.996794 V，而设定是 1.0 V。因此"对设定值"和"对实测输入值"两种口径的增益误差符号相反（-0.156 % / +0.165 %），量级都在 0.2 % 以内。若按传递函数定义（Vout/Vin）算，0.848133 与理论 0.846733 差 +0.165 %，这更接近"电路本身"的精度；对设定值的 -0.156 % 则把源的偏差也算进了电路。
3. 相位实测 -32.225° vs 理论 -32.142°，差 0.083°，与幅值精度同量级，互相印证。

---

## 5. 那次 `V(探针1)` 报错的完整原文

按固定流程，第一次取波形时我故意用了 Multisim 界面上的显示名格式 `V(探针1)` 作为 `probe_id`。完整返回原文如下（stdout 逐字）：

```json
{
  "ok": false,
  "error": {
    "code": "PROBE_NOT_FOUND",
    "message": "'V(探针1)' 是 Multisim 那边的名字，不是 probe_id",
    "hint": "probe_id 是 'P1'。measure / get_waveform 只接受 probe_id；label / output 是只读旁证，不要拿它传参。",
    "context": {
      "field": "probe_id",
      "value": "V(探针1)",
      "available": [
        "P1",
        "P2"
      ],
      "matched": "P1"
    }
  }
}
```

stderr 同时给出：`[agent-cli] #12 get_waveform ERR 16 ms`。

### 我是靠哪个字段改对的

- **`error.context.matched = "P1"`** 是直接给出正确答案的字段——系统已经帮我把 `V(探针1)` 匹配到了唯一探针 `P1`。
- **`error.context.field = "probe_id"`** 说明出错的是哪个参数名（不是 `sim_id`、不是 `max_points`）。
- **`error.context.available = ["P1","P2"]`** 给出了这个仿真里合法的 probe_id 全集，可用来交叉确认。
- **`error.hint`** 明确讲了规则："`label` / `output` 是只读旁证，不要拿它传参"。
- **`error.code = "PROBE_NOT_FOUND"`** 说明这是"找不到通道"，而不是参数类型错、仿真不存在之类的别的问题，所以不需要改参数结构。

于是把 `probe_id` 从 `"V(探针1)"` 改成 **`"P1"`**，重发即成功（`#13 get_waveform ok 3 ms`）。

顺带一个容易踩的坑：`simulate` 的返回里 `outputs` 是 `["V(探针1)","V(探针2)"]`、`probes[].label` 是 `"探针1"`，这些字符串看起来最像"通道名"，但都不能当 `probe_id` 用；能当 `probe_id` 的只有 `add_probe` 时 `name` 给的值（`P1` / `P2`）。`measure` / `get_waveform` 返回的 `channels` 也是以 `probe_id` 为键，两个工具可以直接对照。

---

## 6. 调用统计

| 项 | 数值 |
|---|---|
| 总调用次数 | **16** |
| 其中成功 | 15 |
| 其中报错 | **1** |
| 报错率 | 6.25 % |
| 同样的错犯两次 | **没有** |

调用序列（`trace.jsonl` 的 `seq`，已核验 16 行、`is_error=true` 恰 1 行）：

| seq | 工具 | 结果 |
|---|---|---|
| — | `tools`（枚举，不属于 `call`） | ok，发现 8 个工具 |
| 1 | `create_circuit` | ok → `c-0a8bdb9b95` |
| 2 | `add_component` AC_VOLTAGE V1 | ok |
| 3 | `add_component` RESISTOR_VIRTUAL R1 | ok |
| 4 | `add_component` CAPACITOR_VIRTUAL C1 | ok |
| 5 | `add_component` GROUND GND1 | ok |
| 6 | `connect` `0` 网络 | ok |
| 7 | `connect` `in` 网络 | ok |
| 8 | `connect` `out` 网络（`topology.supported` 变 true） | ok |
| 9 | `add_probe` out → P1 | ok |
| 10 | `add_probe` in → P2 | ok |
| 11 | `simulate` transient（默认窗口） | ok → `s-820fdadf29` |
| **12** | **`get_waveform` `probe_id="V(探针1)"`** | **ERR `PROBE_NOT_FOUND`** |
| 13 | `get_waveform` `probe_id="P1"` | ok |
| 14 | `measure` `s-820fdadf29` all | ok |
| 15 | `simulate` transient（start/stop 指定） | ok → `s-7116e2f2de` |
| 16 | `measure` `s-7116e2f2de` all | ok |

> 另有 2 次只读本地文件的操作（读波形 artifact CSV、跑自写的 `analyze.py`），不属于对执行器的调用，未计入。

**错误处理方式**：全程没有靠猜参数重试。唯一的报错是先读 `error.code` → 判断错误类别，再读 `error.context.field` → 确认是 `probe_id` 传错，再读 `error.context.matched` / `available` → 得到正确值 `P1`，然后只改这一个字段重发。此后所有 `measure` / `get_waveform` 都统一用 `probe_id`，未再犯同类错误。

---

## 附：复现用关键参数

```json
{"circuit_id":"c-0a8bdb9b95","family":"SIGNAL_VOLTAGE_SOURCES","part":"AC_VOLTAGE","refdes":"V1","value":1,"parameters":{"frequency":1000}}
{"circuit_id":"c-0a8bdb9b95","family":"RESISTOR","part":"RESISTOR_VIRTUAL","refdes":"R1","value":1000}
{"circuit_id":"c-0a8bdb9b95","family":"CAPACITOR","part":"CAPACITOR_VIRTUAL","refdes":"C1","value":1e-7}
{"circuit_id":"c-0a8bdb9b95","family":"POWER_SOURCES","part":"GROUND","refdes":"GND1"}
{"circuit_id":"c-0a8bdb9b95","pins":[["V1","2"],["GND1","1"],["C1","2"]]}
{"circuit_id":"c-0a8bdb9b95","pins":[["V1","1"],["R1","1"]]}
{"circuit_id":"c-0a8bdb9b95","pins":[["R1","2"],["C1","1"]],"net":"out"}
{"circuit_id":"c-0a8bdb9b95","target":"out","name":"P1"}
{"circuit_id":"c-0a8bdb9b95","target":"in","name":"P2"}
{"circuit_id":"c-0a8bdb9b95","analysis":"transient"}
```

工作目录内产物：`report.md`（本文件）、`analyze.py`（纯标准库波形分析脚本，只读工具返回的 CSV artifact）、`trace.jsonl`（agent_cli 自动记录）。
