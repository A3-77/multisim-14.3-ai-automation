# Agent Acceptance Report

> 测试者身份：**外部使用者 Agent**（只读 MCP 工具语义，不了解 Multisim 实现）
> 被测对象：`multisim-circuit` MCP Server v0.6.0（7 个工具）
> 时间：2026-10-26
> 约束：全程只走 MCP 协议，未 import 项目任何模块、未调用 msbuild、未构造 Circuit IR、未碰 `.ms14`

---

## 任务

> 创建一个 1V、1kHz 的正弦输入，设计一个截止频率约为 500Hz 的一阶 RC 低通滤波器。
> 自行选择合适的电阻和电容值，创建 Multisim 电路，进行瞬态仿真，
> 并报告输出端的实际幅值、理论幅值以及误差。

### 我的设计决策（不经过 MCP，纯工程判断）

`fc = 1/(2πRC) = 500 Hz` 有无穷多组解。我按 **E12 标准值**选：

| | 值 | 理由 |
| --- | --- | --- |
| R | 10 kΩ | E12 标准值；10k 量级让源内阻影响可忽略 |
| C | 33 nF | E12 标准值；`1/(2π·10k·33n) = 482.3 Hz` |

**fc = 482.288 Hz**（目标 500 Hz，偏 −3.5%）。我没有为了凑 500.0 Hz 去用
非标准值（31.83 nF）—— 真实设计选标准件，偏差要如实报告而不是掩盖。

理论值（1 kHz，fc=482.29 Hz）：
`|H| = 1/√(1+(f/fc)²) = 0.434405`，`∠H = −64.253°`，`Vout = 0.434405 V`

---

## 1. Agent 实际调用了哪些 MCP tools（按顺序）

| # | tool | 结果 |
| --- | --- | --- |
| 0 | `initialize` / `tools/list` | 握手 + 读 schema |
| 1 | `create_circuit` | OK |
| 2–5 | `add_component` × 4 | OK |
| 6–8 | `connect` × 3 | OK |
| 9–10 | `add_probe` × 2 | OK |
| 11 | `simulate` | OK（29.7 s） |
| 12 | `measure` | OK |
| 13 | `get_waveform` | OK |

**主任务 13 次工具调用，零错误，一次通过。**

另有第 14–17 次是我在任务完成后**主动做的错误探测**（明确标注，不属于任务步骤），
以及 8 组 API 边界探测（`out/agent_test/api_probe.json`）。

---

## 2. 每次调用的关键参数

```
create_circuit(name="agent_rc_500hz")                              -> c-eccf480d70
add_component(SIGNAL_VOLTAGE_SOURCES, AC_VOLTAGE, V1, value=1.0, frequency=1000.0)
add_component(RESISTOR,   RESISTOR_VIRTUAL,   R1, value=10000.0)
add_component(CAPACITOR,  CAPACITOR_VIRTUAL,  C1, value=33e-9)
add_component(POWER_SOURCES, GROUND, GND1)
connect(pins=[["V1","+"], ["R1","1"]])              -> 自动命名 "in"
connect(pins=[["R1","2"], ["C1","1"]])              -> 自动命名 "n1"
connect(pins=[["C1","2"], ["V1","-"], ["GND1","1"]])-> 自动命名 "0"
add_probe(target="in")                              -> P1 @ in
add_probe(target="R1.2")                            -> P2 @ n1
simulate(analysis="transient")                      -> s-042f992be7
measure(sim_id=...)                                 -> gain / phase / channels
get_waveform(sim_id=..., max_points=20)             -> 摘要 + artifact
```

---

## 3. 哪一步出现过错误

**主任务（步骤 1–13）：没有错误。**

以下是我主动制造的探测错误（不属于任务流程）：

| # | 调用 | 返回 |
| --- | --- | --- |
| 14 | `add_component(family="INDUCTOR", ...)` | `UNKNOWN_COMPONENT_TYPE` |
| 15 | `simulate(analysis="dc")`（源是 AC_VOLTAGE） | `ANALYSIS_NOT_SUPPORTED` |
| 16 | `add_probe(target="R1")` | `AMBIGUOUS_TARGET` |
| 17 | `add_component(AC_VOLTAGE, 无 frequency)` | `MISSING_PARAMETER` |

---

## 4. 如果出错，我是如何根据 MCP 返回信息恢复的

**主任务没有出错，所以没有"恢复"过程。** 但我确实遇到过一次**真实的恢复**，
发生在 API 边界探测里，值得记录：

### 真实恢复案例

我按 `get_waveform` 的 schema 描述（"只看某个通道的**输出名**"）传了 COM 输出名：

```json
get_waveform(sim_id="s-042f992be7", probe="V(探针1)")
-> ERR PROBE_NOT_FOUND
   message: 没有探针 'V(探针1)'
   hint   : 可用探针：['P1', 'P2']
```

`hint` 直接给出了可用值。我改成 `probe="P1"`，立刻成功。

**这次恢复完全靠 `hint`，不需要猜、不需要读源码。** 这正是错误设计想要的效果。
但根因是 **schema 描述写错了**（见问题 2）。

### 其余探测的可恢复性

| 错误 | 我能靠返回信息恢复吗 |
| --- | --- |
| `UNKNOWN_COMPONENT_TYPE` | 能 —— `context.supported` 列出 5 种可用类型 |
| `ANALYSIS_NOT_SUPPORTED` | 能 —— `hint` 说"把 analysis 改成 'transient'" |
| `AMBIGUOUS_TARGET` | 能 —— `hint` 说"写成 'R1.1' / 'R1.2'" |
| `MISSING_PARAMETER` | 能 —— `context.field = "frequency"` |
| `NO_GROUND` | 能 —— `hint` 说"加一个 POWER_SOURCES/GROUND" |
| `PIN_NOT_FOUND` | 能，但 `context.available` 结构嵌套了一层（见问题 3） |
| `LAYOUT_UNSUPPORTED`（3 个无源元件） | 能 —— `context.count=3, limit=2` |
| `CIRCUIT_NOT_FOUND` / `SIM_NOT_FOUND` | 能 —— 说清该先做什么 |
| `UNKNOWN_TOOL`（我试了 `get_circuit`） | 能 —— 列出 7 个可用工具 |

**9/9 都能恢复。** 这是这次测试里 MCP 最强的一面。

---

## 5. 最终电路是否正确

是。Multisim 注册的两个探针分别落在输入网 `in` 和 RC 中点 `n1`，
仿真出来的波形在起始段明显滞后（电容充电），稳态段是干净的 1 kHz 正弦：

```
t=0.00e+00  vin= 0.000000  vout= 0.000000
t=5.00e-06  vin= 0.031409  vout= 0.000263     <- 输出几乎为 0
t=1.00e-05  vin= 0.062776  vout= 0.001045
t=1.50e-05  vin= 0.094073  vout= 0.002244
t=2.00e-05  vin= 0.125220  vout= 0.004119
```

如果是"电容被短路"或"探针接错网"，输出会和输入同相且等幅 —— 实际不是。

---

## 6. Multisim 是否真实运行

是。证据链（都不是本项目代码的自述，是可独立核对的物证）：

| 证据 | 内容 |
| --- | --- |
| server 启动日志 | `[mcp] multisim-circuit v0.6.0 就绪（python 3.11.9, **32 位**）` |
| `simulate` 耗时 | **29.7 s**（编译 + 启 Multisim + 跑仿真 + 读数；纯计算不会这么慢） |
| 输出名 | `['V(探针1)', 'V(探针2)']` —— 这是 COM `EnumOutputs` 的命名，不是 IR 里的 `P1/P2` |
| `.ms14` 产物 | `agent_rc_500hz.ms14`，**31 799 字节**（真实文件，不是桩） |
| 波形 CSV | **1201 行**（1200 采样点 + 表头），起始段有电容充电的暂态 |
| 独立复算 | 我用纯标准库自己写了最小二乘，从 CSV 复算：gain **0.433288**、phase **−64.327°**，与 `measure` **完全一致** |

最后一条是关键：如果 `measure` 是编出来的数，我不可能从原始波形复算出同一个值。

---

## 7. 实际测量结果

| 项 | 实测 |
| --- | --- |
| 输入幅值 | **0.996791 V**（声明 1 V，拟合偏差 −0.32%） |
| 输入频率 | 1000 Hz（仿真窗口 0~5.995 ms，1200 点，采样率 200 kHz） |
| 输出幅值 | **0.431897 V** |
| 输出相位 | **−64.327°** |
| 增益 | **0.433288** |
| 输出波形峰值 | 0.433265 V（与拟合幅值 0.431897 相差 0.3%，符合正弦拟合的正常范围） |

---

## 8. 理论结果

| 项 | 理论 |
| --- | --- |
| R | 10 000 Ω |
| C | 33 nF |
| fc = 1/(2πRC) | **482.288 Hz** |
| \|H\| @ 1 kHz | **0.434405** |
| ∠H @ 1 kHz | **−64.253°** |
| 输出幅值 | **0.434405 V** |

---

## 9. 误差

| 项 | 实测 | 理论 | 误差 |
| --- | --- | --- | --- |
| 输出幅值 | 0.431897 V | 0.434405 V | **−0.577 %** |
| 增益 | 0.433288 | 0.434405 | **−0.257 %**（相对） |
| 相位 | −64.327° | −64.253° | **−0.074°** |
| fc | 482.288 Hz | 目标 500 Hz | −3.5%（**设计选择**，不是仿真误差） |

**结论：符合一阶 RC 低通理论。** 幅值误差 0.58%、相位误差 0.07°，
远小于 Multisim 的数值精度和拟合精度带来的不确定度。

注意区分两个"误差"：
- **−3.5% 是设计偏差**（我选了标准件 33 nF 而不是 31.83 nF）
- **−0.58% 是仿真/测量误差**（这才是 MCP 链路的质量指标）

---

## 10. 当前 MCP API 是否足够让一个通用 Agent 独立完成这个任务

**够用，但有三处会让 Agent 判断失误的地方。**

正面：

- 7 个工具的语义边界清楚，`tools/list` 的 description 足以让我在**不读源码**的情况下
  决定每次传什么参数
- 坐标完全不用管 —— 我全程没想过"元件放哪"，这是最大的可用性收益
- 错误信息 9/9 都能指导恢复，`hint` 是真能执行的动作，不是"操作失败"
- 每个写操作都返回完整状态快照，我随时知道电路长什么样

负面（详见第 11 项）：三处**命名/结构不一致**，会让 Agent 在"对齐两次调用的数据"时出错。
这些不影响我完成本次任务（因为我每次都读 description），但会影响一个
**不读 description、只看字段名**的 LLM。

---

## 11. 发现的问题（只提问题，未修改任何代码）

按严重程度排序。

### 问题 1（严重）—— `measure` 和 `get_waveform` 的 `channels` 用不同的 key

```json
// measure 返回
"channels": {"P1": {"net":"in", "output":"V(探针1)", ...}, "P2": {...}}

// get_waveform 返回
"channels": {"V(探针1)": {"n":1200, ...}, "V(探针2)": {...}}
```

同一个概念（一个通道），两个工具用两种 key。Agent 想"用 measure 的增益去核对
get_waveform 的波形"时，必须先做一次 `P1 ↔ V(探针1)` 的映射，而这个映射只能
从 `measure.channels.P1.output` 里反查。**这是最容易让 LLM 写错代码的地方。**

建议（供参考，未实施）：两个工具统一用探针名 `P1` 作 key，
COM 输出名放到字段里。

### 问题 2（中）—— `get_waveform` 的 `probe` 描述与实现不一致

- schema：`"只看某个通道的输出名"`
- 实现：只接受探针名（`P1`），传 `V(探针1)` 报 `PROBE_NOT_FOUND`
- 而 `measure` 的同一个参数描述是对的（"探针名，如 P1"）

我实际踩了这个坑（见第 4 节）。能靠 `hint` 恢复，但本来不该发生。

### 问题 3（轻）—— `context` 的结构在不同错误之间不一致

```json
// UNKNOWN_COMPONENT_TYPE：supported 直接是数组
"context": {"supported": ["SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE", ...]}

// PIN_NOT_FOUND：available 是嵌套对象
"context": {"available": {"pins": ["1","2"], "aliases": {"+":"1","-":"2"}}}
```

Agent 写通用错误处理时，`context.available` 有时是数组、有时是对象，
只能每次特殊处理。

### 问题 4（中）—— 没有 `get_circuit`，跨会话无法查状态

7 个工具里没有任何一个能"只读地查一个已有电路现在长什么样"。
写操作会返回快照，所以**单轮任务够用**；但如果 Agent 在两步之间重启、
或者从上一轮对话里只记得 `circuit_id`，就查不到当前状态，只能重建。

我实测 `get_circuit` → `UNKNOWN_TOOL`，`hint` 列出的 7 个工具确实没有它。

### 问题 5（中）—— `simulate` 阻塞且没有进度/超时参数

本次 `simulate` 耗时 **29.7 s**。很多 MCP 客户端默认超时是 60 s。
电路稍微复杂一点（多一个元件、更长窗口）就可能超时，而 Agent 无法区分
"还在跑"和"挂了"——没有 `progress` 通知，也没有 `timeout` 参数。

### 问题 6（轻）—— `add_component` 的 `params` 参数泄漏了内部概念

```json
"params": {"type":"object", "description":"高级用法：直接给底层参数序号。一般不要用"}
```

"参数序号"是 Multisim 的概念。虽然标注了"一般不要用"，但它出现在 schema 里，
LLM 有可能去用它（然后传 `{"5": 1000}` 而不知道 5 是什么）。
与"不暴露 Multisim 内部"的原则有冲突。建议移除或改成更语义的写法。

### 问题 7（信息）—— 拓扑硬墙对"设计类任务"的影响

`LAYOUT_UNSUPPORTED`（并联 / >2 个无源元件）在本次任务里没撞到，
但如果用户的任务是"设计一个分压偏置"或"两级 RC"，Agent 会在 `simulate` 时
被挡住，而**在 `connect` 阶段完全没有任何预警** —— 电路能建出来，只是跑不了。

这不是缺陷（第一版边界明确），但对 Agent 体验有影响：
如果 `connect` 能在"发现拓扑不可能布局"时提前警告，Agent 可以更早改方案，
而不是建完 6 个元件才在最后一步被拒。

### 问题 8（中，发布配图时发现）—— Multisim 渲染不完整：`GetCircuitImage` 画不出 V1 / C1

写发布材料时需要一张电路截图，于是用 COM 的 `GetCircuitImage`（`circ.snapshot`）导出：

| 对象 | 结果 |
| --- | --- |
| 本次生成的 `agent_rc_500hz.ms14` | **只画出 R1 和两个探针**，V1、C1 符号缺失（导线框架是完整的） |
| 让 Multisim 自己 `save_as` 再 reopen 后导出 | 一样缺（37 610 字节的新文件，图 19 470 字节） |
| Multisim 自带样例（`cmp_native_r.png` / `cmp_native_555.png`） | **元件全画出**（53 647 / 34 371 字节） |
| GUI 截图（`guiauto.screenshot`） | 全灰 —— Multisim 是无头启动的，`cls='Multisim14.3'` 窗口 rect 是 `(0,0,0,0)` |

排查过、排除掉的原因：

- **不是时序问题**：立即导出与等 4 s 导出，字节数完全相同（18 142）
- **不是 XML 缺元素**：`dump_symbols.py` 确认 4 个 `CIITSymbolComp` 都有 `Objects` 子节点
- **不是文件没被 Multisim 接受**：仿真照跑、读数照对，说明 Multisim 语义上认这个电路
- **`diag_coords.py`** 在 `CIITSymbolComp` 下没找到带 X/Y 属性的 `Point` 子节点 ——
  说明绘图坐标不是我以为的那套结构，**这条线索停在这里，没有继续挖**

影响：**不影响仿真正确性**（仿真用的是网表，不是图形），但影响"给人看"。
一份生成的电路如果连原理图都画不出来，用户没法目视核对接法。

这也是本次发布里唯一一张"不能直接用"的图 —— 发布配图改成了
从 MCP 会话数据重新绘制的结构图（`out/agent_test/make_circuit_shot2.py`），
Multisim 的真实输出作为缺陷证据保留在 `docs/case/agent_rc_500hz_multisim_render.png`。

---

## 下一步建议

基于这次测试结果，我建议 **A（修 MCP API 的一致性），而不是直接进 P2**。

理由：

1. **主流程零错误 + 错误 9/9 可恢复**，说明 MCP 的骨架是稳的，不需要重做
2. 但问题 1/2/3 是**同一种病**：命名和结构不一致。成本极低（改字段名和描述），
   收益很高 —— 一旦接 LLM，这些不一致会变成"Agent 随机写错代码"，
   而且很难从日志里看出是 API 的问题还是模型的问题
3. 问题 4（`get_circuit`）和问题 5（`simulate` 超时）是**接入 LLM 前必须解决的**
   —— LLM 的多轮对话一定会遇到"我上次建的电路呢"
4. 这些修改**不动任何核心机制**（不碰 `ir_sim` / `ir_compile` / `msbuild` / `mssafe`），
   只动 `circuit_session` 的返回结构和 `mcp_server` 的 schema 描述

修完这 5 个，MCP 才真正算"稳定的执行 API"，那时再做 P2 并联，
或者直接接 LLM 试那句"设计一个 fc=500Hz 的 RC 低通"，风险都小得多。

---

## 附：产物

| 文件 | 内容 |
| --- | --- |
| `out/agent_test/run_task.py` | 任务脚本（外部 Agent 视角） |
| `out/agent_test/mcp_client_min.py` | 我自己写的最小 MCP 客户端（只用标准库） |
| `out/agent_test/trace.json` | 17 次调用的完整轨迹 |
| `out/agent_test/probe_api.py` | API 边界探测 |
| `out/agent_test/api_probe.json` | 8 组探测结果 |
| `out/agent_test/server.log` | server 启动日志（32 位 python） |
| `out/mcp/sessions/c-eccf480d70/` | 电路 IR、`.ms14`、仿真记录、波形 CSV |
