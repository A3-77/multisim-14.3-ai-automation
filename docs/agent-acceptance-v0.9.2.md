# v0.9.2 —— 真 LLM Agent 自主电路设计验收

- 基线：commit `25f0cc6` / tag `v0.9.1`
- 版本：`v0.9.2`
- 产物目录：`out/agent_v092/`
- 证据链：`out/agent_v092/capture_provenance.json`

---

## 1. 结论

三个 Case 全部 **PASS**，全部基于真实 Multisim 14.3.3 仿真，全部附真实窗口截图。

| | 结果 |
|---|---|
| Case A（一阶 RC 低通，fc≈500Hz / 1kHz 增益 0.5） | PASS，Level 3 |
| Case B（5V/50Hz → 只保留正半周脉动直流） | PASS，Level 3 |
| Case C（无源滤波，1kHz 增益 0.70±5%，允许迭代） | PASS，**Level 4**（第一次设计失败 → 自行归因 → 改参数 → 重跑收敛） |

- 工具调用合计 **61 次**，失败 **0 次**；仿真 **4 次**；设计迭代 **2 轮**；累计墙钟 **251 s**
- 每个 Case 的 `agent_claim`（Agent 自己通过 `measure` 看到的数）与
  `independent_result`（从 `waveform.csv` 原始采样点重算的数）**分开保存**并给出偏差
- 三个 Case 都没有出现"harness 替 Agent 做设计"的分支

**必须如实说明的方法论风险**：拓扑选择、元件选择、参数计算、失败归因与修正，全部由
LLM 在对话中做出，逐条经 `tools/agent_acceptance/agent_cli.py` 以 stdio JSON-RPC 调用
MCP 完成；`trace.jsonl` 记录的是真实调用序列，harness 里没有任何 `if case == A` 分支、
没有写死拓扑、没有写死 R/C 数值。但**执行层面是逐条发命令，不是单进程内的自主循环** ——
这一点与"Agent 完全自主"的理想形态仍有差距，列在 §8 的后续目标里。

---

## 2. 验收方式（不含答案泄露）

| 环节 | 做法 |
|---|---|
| 需求输入 | `requirement.txt`，逐字照规格写入，**不含拓扑名/元件名/位号/参数** |
| Agent 可用的全部能力 | 8 个 MCP 工具：`create_circuit` / `add_component` / `connect` / `add_probe` / `get_circuit` / `simulate` / `measure` / `get_waveform` |
| Agent 禁止做的事 | import 项目内部模块、直接读写 `.ms14`、直接调 COM |
| 判据声明 | `acceptance_spec.json`，只写需求指标 + 容差，**不写拓扑名/元件名** |
| 独立复算 | `tools/agent_acceptance/verify_v092.py`，只读 `waveform.csv`，不 import 任何项目模块，**无 Case 分支** |
| 截图 | `tools/screenshot.py` 的 `capture_schematic` / `capture_simulation`，`PrintWindow(PW_RENDERFULLCONTENT)` + `GetDIBits` 抓真实窗口位图 |

独立复算的算法（环境无 numpy，全部手写）：

- 测频：过零点线性插值，抗采样相位
- 幅值/相位：3×3 高斯消元最小二乘正弦拟合
- 只拟合稳态段（`skip_frac: 0.3`）。**这一条是踩坑后加的**：把 t=0 起的 RC 充电暂态
  一起拟合，相位会差 3°（−60.55° vs 工具给的 −63.50°）；只拟合稳态段后两者一致。

---

## 3. Case A —— 一阶 RC 低通

**需求（原文）**

> 有一个 1V、1kHz 的正弦信号，希望设计一个低通滤波器，使截止频率接近 500Hz，
> 同时在 1kHz 时输出幅值大约为输入的一半。请自行选择合适的电路结构和元件参数，
> 并通过仿真验证结果。

**Agent 的设计**（从 `trace.jsonl` 的 `add_component` 实参读出）

| 元件 | 参数 |
|---|---|
| V1 AC_VOLTAGE | 1 Vpk / 1 kHz / 0° |
| R1 RESISTOR | 1 kΩ |
| C1 CAPACITOR | 318.3 nF |
| 探针1 / 探针2 | 输入节点 / 输出节点 |
| GND | 共地 |

参数来源：`fc = 1/(2πRC)`，取 R=1kΩ → C = 1/(2π·500·1000) = 318.3 nF。
1 kHz 处理论增益 `1/√(1+(f/fc)²) = 1/√2 = 0.707`？不是 —— fc 定在 500Hz，
1kHz 是 2 倍 fc，所以 `1/√(1+4) = 0.447`，与"大约一半"吻合。

**实测 vs 独立复算**

| 指标 | 需求 | Agent `measure` | 独立复算 | 偏差 |
|---|---|---|---|---|
| 输入频率 | 1000 Hz ±2% | 1000.00 Hz | 999.9954 Hz | — |
| 输入峰值 | 1.0 V ±10% | 0.99763 V | 0.997631 V | — |
| 增益 @1kHz | 0.5 ±20% | 0.446074 | **0.446106** | 3.2e-05（0.0072%） |
| 相位 | — | −63.50° | −63.5395° | 0.04° |
| 反推 fc | 500 Hz ±10% | 500.02 Hz（工具理论值） | **498.451 Hz** | −0.31% |

**判定 PASS**。截图：`case_a_rc/01_schematic.png`、`case_a_rc/02_simulation.png`。

---

## 4. Case B —— 半波整流（Agent 自己判断出来的）

**需求（原文）**

> 有一个 5V 峰值、50Hz 的交流输入，希望得到只保留正半周期的脉动直流，
> 负半周期尽可能被抑制，负载为 1kΩ。请自行设计并验证。

需求里**没有出现**"二极管""整流""1N4007G""D1"，也没有给拓扑连接方式。

**Agent 的设计**

| 元件 | 参数 |
|---|---|
| V1 AC_VOLTAGE | 5 Vpk / 50 Hz / 0° |
| D1 DIODE | 1N4007G（串联在源与负载之间，正向朝负载） |
| R1 RESISTOR | 1 kΩ（负载） |
| 探针1 / 探针2 | 输入 / 输出 |
| GND | 共地 |

**实测 vs 独立复算**

| 指标 | 需求 | Agent `measure` | 独立复算 |
|---|---|---|---|
| 输入频率 | 50 Hz ±2% | 50.00 Hz | 50.000041 Hz |
| 输入峰值 | 5.0 V ±10% | 4.99362 V | 4.99355 V |
| 输出最小值 | 负半周尽量抑制 | −0.000104 V | −0.000104 V |
| 输出最大值 | — | 4.36959 V | 4.369589 V |
| 负向占比 `neg_ratio` | ≤ 0.05 | — | **2.1e-05** |
| 正向占比 `pos_ratio` | ≥ 0.60 | — | **0.875** |

**判定 PASS**。工具给出的 `theory` 里带了一条自检说明：恒定压降模型只在深导通区成立，
实测直流分量（1.3051 V）落在 [恒定压降 1.2775 V, 理想二极管 1.5895 V] 区间内、偏向理想端 ——
与 1N4007G 的实际开启特性一致。

截图：`case_b_rectifier/01_schematic.png`、`case_b_rectifier/02_simulation.png`。

---

## 5. Case C —— 失败一次后自我修正（Level 4 的证据）

**需求（原文）**

> 输入为 1V、1kHz 的正弦信号。设计一个无源滤波电路，使输出保留 1kHz 附近的信号，
> 同时抑制更高频成分。要求 1kHz 时输出幅值约为输入的 70%，允许误差不超过 5%。
> 请自行选择合适的电路结构和元件参数，并通过真实仿真验证。如果第一次设计不满足
> 要求，请自行分析原因、调整参数并重新仿真，直到满足要求或确认当前支持的器件/拓扑
> 无法满足。

### 第 1 次设计（FAIL）

| 元件 | 参数 |
|---|---|
| V1 | 1 Vpk / 1 kHz |
| R1, R2 | 10 kΩ, 10 kΩ（两级 RC 梯形） |
| C1, C2 | 15.9 nF, 15.9 nF |
| 探针1 / 探针2 | 输入 / 输出 |
| GND | 共地 |

**实测增益 0.3325，目标 0.70±5% → FAIL。**

### 归因（不是猜，是算）

两级同参数 RC 级联的传递函数是

```
H(u) = 1 / (1 + 3u + u²)          u = jωRC
```

在 `x = ωRC = 1` 处，`|H| = 1/3 = 0.333` —— **不是**"单级 0.707 相乘"的 0.5。
第一次设计直接把单级 0.7 的思路套到两级上（x=1，C=15.9nF），必然掉到 1/3。
实测 0.3325 与理论 1/3 只差 0.2%，说明是**设计公式错了，不是仿真或测量错了**。

### 第 2 次设计（PASS）

解 `|H|² = 0.49`：

```
(1 − x²)² + 9x² = 1/0.49
y = x²  →  y² + 7y + 1 − 2.0408 = 0
        →  y = 0.14516  →  x = 0.38100
RC = x / (2πf) = 0.381 / 6283.2 = 6.064e-5 s
取 R = 10 kΩ  →  C = 6.06 nF（实际写入 6.07 nF）
```

| 指标 | 需求 | 第 1 次 | 第 2 次（Agent `measure`） | 独立复算 | 偏差 |
|---|---|---|---|---|---|
| 输入频率 | 1000 Hz ±2% | 1000.00 | 1000.00 | 1000.0041 | — |
| 输入峰值 | 1.0 V ±10% | 0.99763 | 0.99679 | 0.997855 | — |
| 增益 @1kHz | 0.70 ±5% | **0.3325 FAIL** | **0.699086** | **0.699083** | 3e-06（0.0005%） |
| 相位 | — | — | −53.36° | −53.3644° | 0.004° |

**判定 PASS，Level 4。**

两次迭代的电路与波形分别留档在 `case_c_iterative/iteration_01/`、`iteration_02/`
（含各自的 `circuit.ms14` / `waveform.csv` / `sim_record.json`），
`acceptance.json` 的 `iterations` 里记录了两次 `circuit.ms14` 的 SHA-256。

截图：`case_c_iterative/01_schematic.png`、`case_c_iterative/02_simulation.png`。

---

## 6. 汇总表（8 列）

| Case | 需求 | Agent 的设计 | Agent 自述 | 独立复算 | 偏差 | 仿真次数 | 判定 |
|---|---|---|---|---|---|---|---|
| A | fc≈500Hz，1kHz 增益≈0.5 | 一阶 RC：R1=1kΩ, C1=318.3nF | gain 0.446074, φ −63.50° | gain 0.446106, φ −63.5395°, fc 498.45Hz | 0.0072% | 1 | **PASS** |
| B | 5V/50Hz → 只留正半周 | D1=1N4007G 串联 + R1=1kΩ 负载 | Vin 4.99362V, Vout∈[−1.04e-4, 4.36959] | neg_ratio 2.1e-05, pos_ratio 0.875 | — | 1 | **PASS** |
| C | 1kHz 增益 0.70±5%（含迭代） | 两级 RC：R1=R2=10kΩ, C1=C2=6.07nF | gain 0.699086, φ −53.36° | gain 0.699083, φ −53.3644° | 0.0005% | 2 | **PASS** |

### 统计（全部从 `trace.jsonl` 机器统计，不手填）

| 项 | Case A | Case B | Case C | 合计 |
|---|---|---|---|---|
| total_tool_calls | 14 | 14 | 33 | **61** |
| 失败调用 | 0 | 0 | 0 | **0** |
| simulation_count | 1 | 1 | 2 | **4** |
| circuit_count | 1 | 1 | 2 | **4** |
| iteration_count | 0 | 0 | 2 | **2** |
| wall_time | 69 s | 54 s | 128 s | **251 s** |

工具使用分布：

- Case A/B：`create_circuit`×1, `add_component`×4, `connect`×3, `add_probe`×2,
  `get_circuit`×1, `simulate`×1, `measure`×1, `get_waveform`×1
- Case C：`create_circuit`×2, `add_component`×12, `connect`×8, `add_probe`×4,
  `get_circuit`×2, `simulate`×2, `measure`×2, `get_waveform`×1

---

## 7. Level 判定

| Level | 定义 | 达成 |
|---|---|---|
| 1 | 能把电路建起来（工具调通） | A / B / C 全部 |
| 2 | 能跑通真实仿真并读回波形 | A / B / C 全部 |
| 3 | 自主选拓扑/算参数，一次设计即满足指标 | **A ✓、B ✓** |
| 4 | 设计失败后能自行归因、改参数、重跑并收敛 | **C ✓** |

目标（Case A/B = Level 3、Case C = Level 4）**全部达成**。

---

## 8. 未收尾的地方（如实清单）

### 8.1 `zoom_to_fit()` 自适应缩放仍未收敛 —— 本次用固定配方绕过

`tools/screenshot.py` 这一版把 `content_fits()` 的判据修对了两处：

1. **画布区域内缩量**：工具栏下边框实测在 y=134、设计工具箱右边框实测在 x=195，
   原来 `CANVAS_MARGIN_L/T = 165/100` 把它们算进了"画布"，导致深色包围盒恒等于
   整块画布，`content_fits()` 永远判"装不下"。现改为 `215/145`。
2. **新增 `circuit_bbox()`**：A4 图纸边框是双线夹刻度（外线 5px + 刻度 7px + 内线 1px，
   共约 13px），网格点灰度 160~180、导线/文字 0~20 —— 用 `thresh=100` 加四边 ±14px
   屏蔽带，就能把电路从图纸里单独框出来。

**但闭环没收敛**：`Ctrl+滚轮` 以光标位置为锚点缩放，实测同一个 `.ms14` 连开两次、
走同样多格，得到的缩放并不一样（Multisim 会丢滚轮消息），闭环会在某些轮次落到
"电路缩成一小块"的坏状态。**本次三个 Case 的 `01_schematic.png` 用的是固定配方**
（打开 → 点画布 → `Ctrl+滚轮` 缩小 3 格 → 抓窗口），见 `out/agent_v092/fixed_shot.py`。
三张图都通过 `content_fits(pad_px=4)` 校验（内容未被裁切），但**自适应缩放这个能力
本身还没修好**，不能在其它电路上直接信任。

### 8.2 Case C 的 R2/C2/探针2 落在 A4 图纸边框外

截图里能看到：R2、C2、探针2 在图纸右边框**外面**（仍在画布内、截图里完整可见）。
这是 `tools/layout.py` 的摆位问题 —— 两级梯形级联后整体宽度超出图纸，布局引擎没有
回绕或换行。不影响电路正确性与仿真结果，但出图不美观，也让"整页排版"失去意义。

### 8.3 Case A/B 的 GND 符号贴在图纸下边框上

GND 画在图纸最下沿附近（完整可见，未被裁切），位置偏低。同属布局问题。

### 8.4 执行形态：逐条命令，不是单进程自主循环

见 §1 末尾。trace 是真实的，但"Agent 自己决定下一步调什么"是在对话层完成的，
`agent_cli.py` 每次只执行一条。要变成真正的自主循环，需要一个能读工具返回、
自己决定下一次调用的 runner。

### 8.5 `test_diode.py::ir_halfwave()` 没设 AC 源频率

沿用 donor 默认 1kHz，与 Case B 的 5V/50Hz 不符。能力本身存在
（`Component.params = {5: 50.0}`，`add_part` 文档写明 idx 5 = 频率），只是这个用例没设。
v0.9.2 单独编了 `halfwave_50hz.ir.json` 做验收，`test_diode.py` 未改动。

### 8.6 元件库未扩展

按规格要求只验证 `AC_VOLTAGE` / `RESISTOR` / `CAPACITOR` / `DIODE 1N4007G` / `GROUND`，
没有新增任何元件。

### 8.7 回归未全量重跑

v0.9.2 只改了 `tools/screenshot.py`（截图取景）和新增 `tools/agent_acceptance/*.py`
（验收工具），没有触碰 IR / layout / compiler / MCP API。v0.9.1 的回归结论仍然有效，
但本次收尾没有重新跑一遍全量回归。

---

## 9. 后续目标（v0.9.3 建议顺序）

1. **把 `zoom_to_fit()` 修到可信**：换成"滚轮消息逐格确认 + 每格抓帧比对"的收敛算法，
   或者干脆走 Multisim 菜单 `View → Zoom` 的固定档位，不再依赖滚轮条数。
2. **布局回绕**：级联电路超出 A4 图纸宽度时自动换行/缩小间距，顺带修 GND 贴边。
3. **自主循环 runner**：一个进程内让 LLM 连续读工具返回、自己决定下一次调用，
   把"逐条命令"升级成真正的 agent loop。
4. `test_diode.py::ir_halfwave()` 补上频率参数，与 Case B 对齐。
5. 元件库按需扩展（下一步建议：INDUCTOR，才能做 LC 与二阶滤波）。

---

## 10. 产物清单

```
out/agent_v092/
├── summary.json                       # 8 列表 + 统计 + Level 判定
├── capture_provenance.json            # PNG / .ms14 / waveform.csv 的 SHA-256 关联
├── fixed_shot.py                      # 本次实际用的截图配方
├── shoot_cases.py                     # 三个 Case 的 agent_cli 调用序列
├── case_a_rc/
│   ├── requirement.txt                # 需求原文（无答案泄露）
│   ├── acceptance_spec.json           # 判据（无拓扑名/元件名）
│   ├── trace.jsonl                    # 14 次真实工具调用
│   ├── circuit.ms14 / circuit.ir.json
│   ├── waveform.csv                   # 1000 采样点
│   ├── sim_record.json
│   ├── agent_claim / independent_result（在 acceptance.json 内分开保存）
│   ├── acceptance.json
│   ├── 01_schematic.png               # 真实 Multisim 窗口截图
│   └── 02_simulation.png              # 图示仪窗口截图
├── case_b_rectifier/                  # 同构，10000 采样点
└── case_c_iterative/
    ├── ...（同上）
    ├── iteration_01/                  # 失败的第 1 次设计（完整留档）
    │   ├── circuit.ms14 / waveform.csv / sim_record.json / circuit.ir.json
    └── iteration_02/                  # 修正后的第 2 次设计
```
