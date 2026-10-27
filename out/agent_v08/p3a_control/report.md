# RC 低通滤波器瞬态仿真验收报告

- 电路会话：`c-7e579b7c02`（name = `rc_lpf_2k`）
- 仿真句柄：主报告用 `s-696622ee67`（0–3 ms），复核用 `s-36d69b98c4`（0–10 ms）
- 波形 artifact：`out\mcp\sessions\c-7e579b7c02\sims\s-696622ee67.csv`
- 所有"实际值"均来自 `measure` / `simulate` 返回，未做任何估算。

---

## 1. 电路与参数

一阶 RC 低通：1 V 幅值、2 kHz 正弦源 → 串联 1 kΩ → 输出节点 → 100 nF 对地。

| 位号 | family / part | 值 | 说明 |
|---|---|---|---|
| V1 | SIGNAL_VOLTAGE_SOURCES / AC_VOLTAGE | 1.0 V（`value_name = amplitude`），`parameters.frequency = 2000 Hz` | 正弦激励 |
| R1 | RESISTOR / RESISTOR_VIRTUAL | 1000 Ω（`value_name = resistance`） | 串联电阻 |
| C1 | CAPACITOR / CAPACITOR_VIRTUAL | 1e-07 F（`value_name = capacitance`） | 输出节点对地 |
| GND1 | POWER_SOURCES / GROUND | — | 参考地 |

连接（工具自动命名网络）：

- `in`：`V1.1(+)`、`R1.1`
- `out`：`R1.2`、`C1.1`
- `0`：`V1.2(-)`、`C1.2`、`GND1.1`

探针：`Vin` → 网络 `in`（Multisim 输出 `V(探针1)`）；`Vout` → 网络 `out`（`V(探针2)`）。

后端拓扑判定：`kind = bypass`，`n_series = 1`，`n_shunt = 1`，`out_net = out`，`supported = true`。

仿真设置（显式给定，未用自动推算）：`analysis = transient`，`start = 0`，`stop = 0.003`，`sample_rate = 400000 Hz` → `n = 1200` 点，时间范围 0 – 2.9975 ms（6 个周期）。
耗时：layout 0.013 s / compile 15.733 s / run 4.48 s / total 20.226 s。Multisim 回读元件值：`R1 = 1000.0 Ω`，`C1 = 1e-07 F`（与设定一致）。

---

## 2. 实际值（工具返回）

`measure(s-696622ee67, what=all)`，`mode = ratio`（以实测 Vin 幅值为基准，`source_amp = 1.0`，`source_freq = 2000.0`）：

| 量 | 值 |
|---|---|
| 实际增益（ratio 模式） | **0.6214528** |
| 实际相位 | **−51.5783 °** |
| 输出幅值（Vout 正弦拟合 `amp`） | **0.6194585 V** |
| 输入幅值（Vin `amp`） | 0.9967909 V |
| Vout min / max / mean / rms | −0.6204207 / 0.6900895 / 0.0164329 / 0.4423786 V |
| Vin min / max / mean / rms | −0.9976408 / 0.9976408 / 1.89e−06 / 0.7048383 V |
| Vout 拟合 `offset` | −2.10e−06 V |

复核仿真（0–10 ms，20 个周期，n = 4000）：增益 **0.6214495**，相位 **−51.5780 °**，Vout 幅值 **0.6194548 V**（min/max 与首次完全相同，说明结果确定性、且与窗口长度无关）。

---

## 3. 理论值（自己用标准库算）

用 `calc_theory.py`（纯 `math`，仅算自己的公式）：

```
fc   = 1/(2πRC)          = 1591.5494 Hz
ωRC  = 2π·2000·1000·1e-7 = 1.2566371
|H|  = 1/√(1+(ωRC)²)     = 0.6226770
φ    = −arctan(ωRC)      = −51.4881 °
Vout = 1 V × |H|         = 0.6226770 V
```

| 量 | 理论值 |
|---|---|
| 截止频率 fc | 1591.5494 Hz |
| 理论增益 | **0.6226770**（−4.1147 dB） |
| 理论相位 | **−51.4881 °** |
| 理论输出幅值 | **0.6226770 V** |

（工具 `measure` 返回的 `theory` 块独立给出 `gain = 0.6226769923`、`phase_deg = −51.4881127`、`fc = 1591.5494309`，与我自算的数值一致到 1e−10。）

---

## 4. 误差

| 量 | 实际 | 理论 | 绝对误差 | 相对误差 |
|---|---|---|---|---|
| 增益 | 0.6214528 | 0.6226770 | −0.0012242 | **−0.197 %** |
| 相位 | −51.5783 ° | −51.4881 ° | −0.0901 ° | 0.175 %（相对 51.49°） |
| 输出幅值 | 0.6194585 V | 0.6226770 V | −0.0032185 V | **−0.517 %** |
| 输入幅值（对照） | 0.9967909 V | 1.0000000 V | −0.0032091 V | −0.321 % |

复核运行（0–10 ms）：增益 0.6214495（−0.197 %），相位 −51.5780 °（−0.0899 °），幅值 0.6194548 V（−0.518 %）——与首次几乎逐位相同，误差不是随机噪声。

误差来源分析（基于工具返回的数字，不猜测内部实现）：

1. 增益误差在 ratio 模式下仍为 −0.2 %，而输入幅值本身偏低 −0.32 %，两者量级相当，指向**正弦拟合的幅值估计偏差**：400 kHz 采样、2 kHz 信号（每周期 200 点）下，拟合出的幅值系统性偏小；增益是两通道幅值之比，偏差只部分抵消，所以残留 −0.2 %。
2. 相位误差 −0.09° = −0.00157 rad，而每采样点的相位步进为 2π/200 ≈ 0.0314 rad，即误差仅约 0.05 个采样间隔，处于采样/拟合分辨率的量级内。
3. 输出波形 min = −0.6204、max = +0.6901，关于零明显不对称，mean = 16.4 mV：这是 t = 0 时电容零初始状态引起的指数启动项（τ = RC = 100 µs）尚未完全衰减的痕迹。但它**不是**增益偏差的原因——把窗口从 3 ms 拉长到 10 ms 后增益只从 0.6214528 变到 0.6214495（变化 5e−6），误差稳定在 −0.197 %。
4. 结论：仿真与一阶 RC 理论在 0.2 % / 0.1° 内一致，量级符合"数值仿真 + 波形拟合"的精度预期，无系统性建模错误。

---

## 5. 报错记录

**本次验收过程中没有任何一次工具调用报错。** 15 次调用全部返回 `ok: true`，`error` 字段从未出现。

因此本节无 code / message / hint / context 可贴，也无"根据某字段修改参数后重试"的过程。为避免空口断言，说明一下为什么没触发错误（都是按 schema 的显式约束提前规避的，而非试错）：

- `add_component` 的 `parameters` 键用语义名 `frequency`（而非数字序号），并且用了文档给的便捷写法 `frequency` 顶层字段，**没有同时传** `parameters`——schema 明确写了"两者等价，不要同时传"。
- `add_component` 不传坐标；`refdes` 显式给（V1/R1/C1/GND1）。
- `GROUND` 按 schema 不传 `value`（返回里 `value/value_name/value_unit` 均为 `null`，符合预期）。
- `connect` 的 `pins` 用 `[["V1","+"],["R1","1"]]` 形式的数组对，未用字符串混写。
- `add_probe` 的 `target` 只用网络名（`in` / `out`），没有传元件位号（schema 警告会 `AMBIGUOUS_TARGET`）；探针数 2 ≤ 9。
- `simulate` 的 `analysis` 与源类型匹配（AC_VOLTAGE → transient），未触发 `ANALYSIS_NOT_SUPPORTED`。
- `measure` / `get_waveform` 的 `probe_id` 用的是 `add_probe` 时自定的 `Vin` / `Vout`，不是 Multisim 显示名 `探针1/2`，也没有传输出名 `V(探针1)`，因此没触发 `PROBE_NOT_FOUND`。
- 拓扑在搭完地线后就已 `supported = true`（`bypass`），所以没有 `LAYOUT_UNSUPPORTED`。

---

## 6. 调用统计

| 项 | 数量 |
|---|---|
| 总调用次数 | **15**（电路执行器工具调用；另有 1 次 `tools` 列举，合计 16 条命令） |
| 报错次数 | **0** |
| 同一错误犯两次 | **无（0 次报错，故不存在）** |

调用明细（顺序）：

1. `tools` — 列出 8 个工具
2. `create_circuit` → `c-7e579b7c02`
3. `add_component` V1（AC_VOLTAGE, 1 V, 2000 Hz）
4. `add_component` R1（1000 Ω）
5. `add_component` C1（1e−7 F）
6. `add_component` GND1（GROUND）
7. `connect` `in` = V1.1, R1.1
8. `connect` `out` = R1.2, C1.1
9. `connect` `0` = V1.2, C1.2, GND1.1 → 拓扑 `supported = true`
10. `add_probe` Vin（net `in`）
11. `add_probe` Vout（net `out`）
12. `simulate` transient 0–3 ms @400 kHz → `s-696622ee67`（20.2 s）
13. `measure` `s-696622ee67` what=all → 主结果
14. `get_waveform` `s-696622ee67` probe=Vout → 摘要 + CSV artifact 路径
15. `simulate` transient 0–10 ms @400 kHz → `s-36d69b98c4`（19.8 s）
16. `measure` `s-36d69b98c4` what=all → 复核

（明细含 `tools` 自身共 16 条命令；其中对电路执行器的工具调用为 15 次：create 1 + add_component 4 + connect 3 + add_probe 2 + simulate 2 + measure 2 + get_waveform 1。）

---

## 结论

在 1 V / 2 kHz 激励下，R = 1 kΩ、C = 100 nF 的 RC 低通：

- **实际增益 0.62145**，理论 **0.62268**，误差 **−0.197 %**
- **实际相位 −51.578°**，理论 **−51.488°**，误差 **−0.090°**
- **实际输出幅值 0.61946 V**，理论 **0.62268 V**，误差 **−0.517 %**

全部误差在 0.2 % / 0.1° 量级内，且对窗口长度不敏感（3 ms 与 10 ms 结果一致到 5e−6），仿真结果可信。全程 15 次调用、0 次报错。
