# v0.8.0 Agent Acceptance：LLM → MCP → Multisim

> **这次测的不是"后端能不能跑"，而是"一个只见过 `tools/list` 的 LLM，能不能自己跑完"。**
>
> v0.7.0 已经把二阶 RC 梯形跑通（增益 0.583062 / 相位 −64.705°，理论 0.584342 / −64.581°），
> 但那是**脚本**在跑。脚本知道 R 该取多少、知道先 `add_component` 再 `connect`、
> 知道探针要放两个。LLM 不知道。
>
> 所以 v0.8.0 的题目是：**把 API 文档（`tools/list` 的 schema + description）丢给一个
> 完全不了解 Multisim 内部实现的 LLM Agent，看它能不能自己设计、自己建模、自己仿真、
> 自己验算 —— 以及出错时能不能只靠 `error.hint` 自己爬回来。**

| | |
| --- | --- |
| 被测服务 | `multisim-circuit` MCP Server **v0.7.0**（8 个工具，测试期间**未改一行 API**） |
| Agent | 通用 LLM Agent，独立上下文，只拿到「任务原文 + CLI 用法 + 禁止事项」 |
| 交互方式 | 只用 `initialize` / `tools/list` / `tools/call`，一条 JSON-RPC 一条命令 |
| 真机 | Multisim 14.3（Circuit Design Suite 14.3）+ 32 位 Python 3.11.9 |
| 日期 | 2026-10-27 |
| 规模 | **5 轮独立任务 / 128 次工具调用 / 11 次真实 Multisim 仿真 / 3 次报错（全部自愈）** |

---

## 0. 一句话结论

**能。** 五个任务里两个零报错（一阶 / 二阶），另外三个各踩一次错 —— 其中两个是测试台故意
注入的，一个是后端真实的能力边界；三次都在**一次尝试内改对**，没有一次重复同类错误。

更重要的是：**它把三个我们自己没测出来的 API 缺陷挖出来了** —— 其中
`measure` 的增益方向按探针添加顺序配对，会让"先放输出探针"的电路得出 `gain = 1/真值`、
相位符号翻转，而返回里 `mode="ratio"` + `in_probe`/`out_probe` 看起来完全权威。
v0.6.1 / v0.7.0 两次验收都没发现，因为那两次恰好都是"先加输入探针"。

这就是接 LLM 的价值：**它不会照着测试脚本的假设走。**

---

## 1. 测试环境

| 项 | 值 |
| --- | --- |
| OS | Windows（win32） |
| Multisim | 14.3，`C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3` |
| Python | `runtime/py32/python.exe` —— 3.11.9，**32 位**（COM 限制） |
| MCP Server | `multisim-circuit` **v0.7.0**（验收期间版本号未变） |
| 传输 | stdio，一行一个 JSON-RPC 2.0 |
| 协议版本 | `2024-11-05` |
| Agent 模型 | 通用 LLM（独立上下文，无项目记忆） |
| 测试台 | `tools/agent_acceptance/`（本次新增，纯标准库） |

### 1.1 测试台做了什么

| 文件 | 职责 |
| --- | --- |
| `mcp_stdio.py` | 起 server 子进程、发一行 JSON、读一行 JSON。**不 import 项目任何模块** |
| `agent_cli.py` | Agent 唯一入口：`tools` / `schema` / `call`；每次调用写一条 `trace.jsonl` |
| `summarize.py` | trace → 调用序列表格 + 统计（错误数 / 重复调用 / 耗时） |
| `verify_sim.py` | 不信 `measure`：从原始 CSV 独立重算 amp / phase 并对账 |

一个刻意的设计：**一个 CLI 进程 = 一次工具调用**。server 是无状态的（电路在磁盘上），
所以 Agent 没法依赖进程内的隐藏状态 —— 它必须真的把 `circuit_id` / `sim_id` 带过去。
这正是"多轮对话里记不记得住上下文"的实测。

---

## 2. 测试约束，以及怎么证明它没被违反

题目要求的六条禁令，逐条给证据：

| 约束 | 怎么证明 |
| --- | --- |
| 只通过 MCP JSON-RPC 交互 | 每次调用都在 `trace.jsonl` 里有一行；`seq` 连续无缺号。Agent 的所有"实际值"都能在 trace 里找到出处 |
| 不 import 项目模块 | Agent 自己写的分析脚本只有 `import csv` / `math` / `cmath` / `sys`（`grep` 全目录可复核）。`p1/fit.py`、`p1/dft.py`、`p2/analyze.py`、`p3b/analyze.py` |
| 不调 `msbuild` | trace 里没有任何一次越权调用；产物 `.ms14` 只由 `simulate` 生成（`compile.bytes` 可查） |
| 不构造 Circuit IR / 不编辑 `.ms14` | Agent 的 workdir 里没有任何 `.ms14` 或 `circuit.ir.json`；它连 `out/mcp/sessions/` 都没进去过（只读工具返回的 CSV artifact） |
| 不直接操作 Multisim COM | 同上；且 COM 只在 server 进程内发生，CLI 进程只做 stdin/stdout |
| 不读源码/文档辅助完成 | 见下面的说明 |

**关于最后一条，说实话**：这不是内核级沙箱，无法从技术上证明它没打开过 `tools/`。
能给的证据是三条：

1. 它的行为像一个**不知道内部实现**的使用者：把 `topology.kind="bypass"` 当成意外发现来讨论、
   猜测 `start` 是"被忽略还是只影响内部求解"、把 `preview` 的抽样混叠误判成"数据错位"——
   读过 `layout.py` / `circuit_session.py` 的 Agent 不会犯这个误判。
2. 它自己写的脚本只依赖 CSV 和标准库，没有任何一行借用项目代码。
3. 报告里凡是"实际值"都能在 trace 里对上（下面第 5 节有对账表），没有一处是编的。

---

## 3. 阶段一：一阶 RC（1 V / 1 kHz，fc ≈ 500 Hz）

**任务原文**（与 v0.6.1 完全一致，保证可比较）：

> 创建一个 1V、1kHz 的正弦输入，设计一个截止频率约为 500Hz 的一阶 RC 低通滤波器。
> 请自行选择合适的电阻和电容值，创建 Multisim 电路，进行瞬态仿真，
> 并告诉我输出端的实际幅值、理论幅值以及误差。

没有给 R、C、拓扑、调用顺序、理论公式。

### 3.1 A. 需求理解

| 项 | 结果 |
| --- | --- |
| 1 V / 1 kHz 正弦输入 | ✅ `AC_VOLTAGE value=1.0, parameters={"frequency":1000}` |
| fc ≈ 500 Hz | ✅ 自己算 τ = 1/(2π·500) = 318.31 µs 再选标准件 |
| 一阶 RC 低通 | ✅ 串联 R + 电容到地，输出取电容两端（并解释了"取电阻两端就是高通"） |
| 需要仿真 + 实际/理论对比 | ✅ 自己写了 `fit.py` 做最小二乘、`dft.py` 做整周期 DFT、`verify.py` 校验时间轴 |

### 3.2 B. 元件设计（它自己选的）

| 项 | 值 |
| --- | --- |
| R | **1 kΩ**（E12） |
| C | **330 nF**（E12） |
| 实际 fc | **482.288 Hz** |
| 相对 500 Hz | **−3.54%**（设计偏差，非仿真误差） |
| 选值理由 | 1k×330n = 330 µs 是 E12 里最接近 318 µs 的组合；次优 1k×300n 偏 +6%；1.6k+200n 虽只差 −0.5%，但 200 nF 不在 E12 且不易采购 |

> 与 v0.6.1 的 Agent 选的（10 kΩ / 33 nF）不同，但 fc 完全相同（482.29 Hz）——
> 同一道题的不同标准值组合，都合理。这正是"不要因为没选你预期的 R/C 就判错"的例子。

### 3.3 C. MCP 调用序列（15 次，零错误）

| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=rc_lpf_500hz | ok | 4 ms |
| 2 | `add_component` | V1 AC_VOLTAGE 1 V @1 kHz | ok | 14 ms |
| 3 | `add_component` | R1 1000 Ω | ok | 17 ms |
| 4 | `add_component` | C1 3.3e-7 F | ok | 16 ms |
| 5 | `add_component` | GND1 | ok | 16 ms |
| 6 | `connect` | V1.+ / R1.1 → net `in` | ok | 18 ms |
| 7 | `connect` | R1.2 / C1.1 → net `out` | ok | 17 ms |
| 8 | `connect` | V1.- / C1.2 / GND1.1 | ok（自动命名 `0`） | 17 ms |
| 9 | `add_probe` | `in` → P_in | ok | 18 ms |
| 10 | `add_probe` | `out` → P_out | ok | 16 ms |
| 11 | `simulate` | transient，start=2 ms / stop=6 ms / 200 kHz / timeout=240 s | ok | 20.5 s |
| 12 | `measure` | all | ok | 95 ms |
| 13 | `get_waveform` | all | ok | 4 ms |
| 14 | `simulate` | transient，stop=12 ms（想拉长稳态窗） | ok | 20.0 s |
| 15 | `measure` | all | ok | 88 ms |

完整表（含每次的 args / result）：[`out/agent_v08/p1/calls.md`](../out/agent_v08/p1/calls.md)，
原始日志 [`trace.jsonl`](../out/agent_v08/p1/trace.jsonl)。

**观察**：

- **`probe_id` 理解正确**：两次 `add_probe` 都给了语义名（`P_in` / `P_out`），后面
  `measure` / `get_waveform` 一次都没传错 —— 它读懂了"不要用 `V(探针1)`"那句 description。
- **`get_circuit` 一次没调**：不是不会，而是**不需要** —— 每个变更类工具都返回完整快照。
  这是 v0.6.2 的设计意图（"不需要额外的 get_circuit 也能知道电路长什么样"）。
  后面阶段三的 Agent 在 4 个电路之间切换时用了 4 次 `get_circuit` 来核对，说明这个工具在
  **多电路场景**下才有价值。
- **无意义重复调用 0 次**，**参数猜测 0 次**（15 次全部一次成功）。
- 第 11 次它传了 `start=0.002` 想跳过启动暂态，拿到 `get_waveform` 后发现时间轴仍从 0 开始；
  第 14 次改成"拉长 stop 到 12 ms + 自己在分析侧截窗"，两次增益差 1.5e-5。
  它在报告里点名"`start` 传了不报错也不生效"—— 这是 v0.8.0 修掉的第二个缺陷。

### 3.4 D. 仿真验证：它真的跑了吗

| 证据 | 内容 |
| --- | --- |
| `timing` | layout 0.009 s / compile 15.585 s / run 4.444 s / total **20.038 s** |
| `.ms14` | 31 784 字节（真实工程文件，不是桩） |
| 波形 CSV | **2400 行**，5 µs 均匀采样，t ∈ [0, 0.011995] |
| Multisim 回读的元件值 | `R1=1000.0`、`C1=3.3e-07` —— 值真的进了网表 |
| 输出名 | `['V(探针1)', 'V(探针2)']` —— COM `EnumOutputs` 的命名，不是 IR 里的 `P_in/P_out` |
| **独立复算** | `verify_sim.py` 从 CSV 重做最小二乘，与 `measure` 的 amp / phase **差值为 0**（`checks.recompute.consistent=true`） |

最后一条是关键：**如果 `measure` 是编的数，从原始 CSV 不可能复算出同一个值。**
复算结果：[`out/agent_v08/p1/verify_s22aa89a47f.json`](../out/agent_v08/p1/verify_s22aa89a47f.json)，
原始波形：[`out/agent_v08/p1/evidence/waveform.csv`](../out/agent_v08/p1/evidence/waveform.csv)。

### 3.5 E. 理论验证（Agent 自己算的）

它自己用纯标准库算：`fc = 1/(2πRC)`、`|H| = 1/√(1+(f/fc)²)`、`φ = −arctan(f/fc)`。

| 量 | 实测 | 理论 | 绝对误差 | 相对误差 |
| --- | --- | --- | --- | --- |
| 输入幅值 | 0.996793 V | 1.000000 V | −3.21 mV | −0.321% |
| 输出幅值 | **0.431883 V** | 0.434405 V | −2.52 mV | **−0.581%** |
| 增益 | **0.433272** | 0.434405 | −1.133e-3 | **−0.261%** |
| 相位 | **−64.3247°** | −64.2526° | −0.0721° | — |

它自己把误差拆成了两层（这是"理解结果"而不是"打印结果"的直接证据）：

- **−0.32% 是激励幅度亏损**：源设 1.000 V，导出的基波只有 0.99679 V。四个阶段、十几次仿真里
  这个数**稳定在 0.99679**，与负载无关（11 kΩ 和 1 kΩ 负载下一样），所以不是分压，是读数/插值路径
  的固定标度偏差。
- **−0.261% 才是传递函数的仿真误差**：用增益（幅值比）衡量时，激励亏损自动抵消。
- **−3.54% 是设计偏差**：选了 330 nF 而不是 318.3 nF，与仿真无关。

---

## 4. 阶段二：二阶 RC（1 kHz 输入，fc ≈ 2 kHz）

**任务原文**：

> 设计一个 1kHz 正弦输入经过二阶低通滤波器，截止频率约 2kHz，
> 要求输出幅值和理论值进行验证。请自行选择合适的标准电阻和电容值，并完成 Multisim 仿真。

没有说"两个 R 两个 C"，没有说拓扑。

### 4.1 它自己判断出来的东西

| 判断 | 内容 |
| --- | --- |
| 可用元件 | 只有 R / C / 源 / 地 —— 没有运放、没有电感 |
| 因此 | Sallen-Key / MFB / RLC 全部不可用，**只能两节 RC 级联** |
| 怎么保证真是二阶 | 两只电容**不共节点**（C1 在 mid、C2 在 out）→ 两个独立状态变量 → 分母二次 |
| 关键取舍 | 无源级联有**加载效应**，`H ≠ H1·H2`，必须用含 `R1C2` 项的完整二阶式 |

它算出的分母：`D(s) = 1 + 9.87e-5·s + 2.209e-9·s²`，双实极点 2471 Hz / 4640 Hz，高频 −40 dB/dec。
并指出：无源两级 RC 的 `Q = √(τ1τ2)/(τ1+τ2+R1C2) ≤ 0.5`，**永远做不出 Butterworth 的 0.707**，
所以 fc 必须按 −3 dB 定义，不能拿 `f0 = 1/(2π√(R1C1R2C2))` 冒充。

### 4.2 元件与 fc

| 项 | 值 |
| --- | --- |
| R1 / R2 | **1 kΩ / 10 kΩ** |
| C1 / C2 | **47 nF / 4.7 nF** |
| τ1 / τ2 | 47 µs / 47 µs（刻意相等，Q 取到 0.4762） |
| fc（−3 dB） | **2034.3 Hz**（目标 2000，**+1.71%**） |
| f0（自然频率） | 3386.3 Hz —— 它明确说这不是 fc |
| 交叉验证 | 另建同拓扑、源频改 2 kHz 的电路实测增益 0.712588，理论 0.713855（−0.178%），自洽证明 −3 dB 点确实略高于 2 kHz |

### 4.3 调用与仿真

31 次调用（两个电路：主电路 16 次 + 交叉验证电路 15 次），**0 报错**，2 次真机仿真。

| 项 | 主电路 |
| --- | --- |
| circuit_id | `c-44ba97b68d` |
| sim_id | `s-29160bf3e9` |
| 拓扑判定 | `kind="ladder"`, n_series=2, n_shunt=2 —— **v0.7.0 的 branch-aware layout 被 LLM 真的用上了** |
| timing | layout 0.016 / compile 18.023 / run 5.683 / total **23.722 s** |
| `.ms14` | 38 054 字节 |
| 波形 | 1600 行，5 µs，t ∈ [0, 0.007995] |
| 独立复算 | amp / phase 与 `measure` **差值 0** |

### 4.4 实测 vs 理论

| 量 | 实测 | 理论 | 相对误差 |
| --- | --- | --- | --- |
| 输出幅值 | **0.902741 V** | 0.906184 V | −0.380%（对 1 V 标称） |
| 增益（对实测输入归一） | **0.905646** | 0.906184 | **−0.0594%** |
| 相位 | **−34.2947°** | −34.1922° | −0.1025° |

它把 −0.380% 拆成 −0.321%（激励亏损）+ −0.059%（滤波器本身），和阶段一的结论一致 ——
**同一个系统性偏差在两道不同的题上被独立识别出来**，这不是巧合，是它真的在分析。

---

## 5. 阶段三：错误恢复（三个 Case）

> 成功路径已经证明。这一段测的是：**报错信息对 LLM 到底有没有用。**

### Case 1：缺参数（`MISSING_PARAMETER`）

**怎么造**：测试台在**第一次** `add_component` 一个 `AC_VOLTAGE` 时，把 `frequency` 和
`parameters` 从参数里摘掉（`--profile p3a`，只注入一次，trace 里记 `"injected"`）。
Agent 不知道这回事 —— 它以为是自己传错了。

**任务**：1 V / 2 kHz 源 → 1 kΩ 串联 → 100 nF 到地，报告 2 kHz 处增益 / 相位与误差。

**报错原文**（trace 第 2 条）：

```json
{"ok": false, "error": {
  "code": "MISSING_PARAMETER",
  "message": "AC_VOLTAGE 需要 frequency（单位 Hz）",
  "hint": "add_component 里传 parameters={'frequency': <数值>}。",
  "context": {"part": "AC_VOLTAGE", "field": "frequency", "supported": ["frequency"]}}}
```

**恢复过程**：读到 `hint` + `context.field` → 把顶层 `"frequency": 2000` 改成
`"parameters": {"frequency": 2000}` → 重试成功 → 之后所有调用都保持这个写法。

| 指标 | 值 |
| --- | --- |
| 调用 | 14 次（13 成功 / 1 报错） |
| 同类错误重复 | **0** |
| 结果 | 增益 0.621456 vs 理论 0.622677（−0.196%）；相位 −51.578° vs −51.488°（−0.090°） |

**对照组**：同一个任务、**不开注入**，另一个 Agent 跑出 15 次调用 0 报错
（[`out/agent_v08/p3a_control/`](../out/agent_v08/p3a_control/)）。
所以这次报错确实来自注入，不是任务本身有坑。

### Case 2：错误探针名（`PROBE_NOT_FOUND`）

**怎么造**：任务里明确要求"第一次取波形时故意用 `V(探针1)`"，这是 v0.6.1 真实踩过的坑。

**报错原文**：

```json
{"ok": false, "error": {
  "code": "PROBE_NOT_FOUND",
  "message": "'V(探针1)' 是 Multisim 那边的名字，不是 probe_id",
  "hint": "probe_id 是 'P1'。measure / get_waveform 只接受 probe_id；label / output 是只读旁证，不要拿它传参。",
  "context": {"field": "probe_id", "value": "V(探针1)", "available": ["P1","P2"], "matched": "P1"}}}
```

**恢复过程**：`context.matched` 直接给出 `P1`，`context.available` 给出全集，`hint` 讲清规则 →
把 `probe_id` 改成 `P1`，一次成功。它特别指出：`simulate.outputs` 里的 `V(探针1)` 和
`probes[].label` 里的 `探针1` 最像"通道名"，但都不能当 `probe_id` 用。

| 指标 | 值 |
| --- | --- |
| 调用 | 16 次（15 成功 / 1 报错） |
| 同类错误重复 | **0** |
| 结果 | 输出幅值 0.845410 V vs 理论 0.846733 V（−0.156%） |

### Case 3：不支持的拓扑（`LAYOUT_UNSUPPORTED`）

**怎么造**：题目本身合理但踩边界 —— 输出节点对地挂 **10 kΩ ∥ 10 nF**（并联到地）。

**报错原文**：

```json
{"ok": false, "error": {
  "code": "LAYOUT_UNSUPPORTED",
  "message": "网络 'out' 有 2 个到地元件（R2, C1），是并联到地",
  "hint": "P2 每一级最多一个到地元件。两个元件并联到地（比如电阻和电容并联）还没验证过；拆成一个元件，或先用两个电路分别验。",
  "context": {"reason": "parallel_shunt", "net": "out", "shunts": ["R2", "C1"]}}}
```

**它的判断（逐条对上了要求）**：

| 要求 | 实际表现 |
| --- | --- |
| 理解 `LAYOUT_UNSUPPORTED` | ✅ 指出报错发生在**布局阶段**（总耗时 1 ms，编译都没进） |
| 读 `reason` | ✅ `parallel_shunt` |
| 理解 `hint` / `context` | ✅ 引用"两个元件并联到地……还没验证过"作为能力边界的证据 |
| 不胡乱改电路 | ✅ 原电路 `c-65aef7c37f` **一字未改**，没有偷偷删掉 R2 去凑一个能跑的电路 |
| 向用户解释"电路合理但后端不支持" | ✅ "R∥C 是教科书式一阶 RC 低通 + 直流泄放通路，电学合法，理论有闭式解 0.907611 V" |
| 主动换成等价但受支持的拓扑 | ✅ **拆成两个可仿真电路**：分压（K=R2/(R1+R2)）+ 极点（τ=C·(R1∥R2)），用恒等式相乘还原 |

它给出的替代验证（3 个子电路、4 次真机仿真）：

| 子电路 | 实测增益 | 理论 | 相对误差 |
| --- | --- | --- | --- |
| A 分压 R1=1k / R2=10k | 0.909090908 | 0.909090909 | 9.7e-10 |
| B RC 1k / 10nF | 0.998019476 | 0.998031905 | 1.25e-5 |
| C 极点 909.09 Ω / 10nF | 0.998362653 | 0.998372642 | 1.00e-5 |
| **A×C 还原** | **0.907602 ∠ −3.280°** | **0.907611 ∠ −3.269°** | **1.0e-5 / 0.011°** |

并且它主动声明了边界："0.907602 是由两个实测子结果按恒等式合成的，不是对 R∥C 网络的一次直接瞬态测量"。

| 指标 | 值 |
| --- | --- |
| 调用 | 52 次（51 成功 / 1 报错） |
| 同类错误重复 | **0** |
| 无意义重复 | 1 次（连续两次 `get_circuit`，只读、幂等，无副作用） |
| 乱改电路 | **0** |

---

## 6. 阶段四：Agent 的自主分析能力（13 项）

要求每个 Agent 交一份工程报告，至少覆盖 13 项。逐项对照：

| # | 要求 | 阶段一 | 阶段二 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | 电路设计 | ✅ | ✅ | 都解释了"为什么是这个拓扑"，阶段二还论证了"为什么只能是这个拓扑" |
| 2 | R / C 参数 | ✅ | ✅ | 都标明是否标准值 |
| 3 | 实际截止频率 | ✅ 482.288 | ✅ 2034.3 | 阶段二自己定义了 −3 dB 口径，拒绝拿 f0 冒充 |
| 4 | 输入参数 | ✅ | ✅ | 幅值 / 频率 / 仿真窗口 |
| 5 | 输出实际幅值 | ✅ 0.431883 | ✅ 0.902741 | 都给了拟合值与峰值两种口径 |
| 6 | 理论输出幅值 | ✅ 0.434405 | ✅ 0.906184 | 自己算，不是抄 `theory` 字段 |
| 7 | 实际增益 | ✅ 0.433272 | ✅ 0.905646 | 阶段二用通道 amp 相除，绕开了当时有 bug 的 `gain` |
| 8 | 理论增益 | ✅ | ✅ | |
| 9 | 实际相位 | ✅ −64.3247° | ✅ −34.2947° | |
| 10 | 理论相位 | ✅ −64.2526° | ✅ −34.1922° | |
| 11 | 误差 | ✅ | ✅ | **都区分了"设计偏差 / 激励偏差 / 仿真误差"三层** |
| 12 | 仿真是否成功 | ✅ | ✅ | 都不是只看 `ok:true`，而是给 5~6 条交叉证据 |
| 13 | 失败原因 | ✅（未失败） | ✅（未失败） | 阶段三单独覆盖失败路径 |

**"在理解结果，还是只把数据打印一遍"** —— 三条硬证据：

1. 阶段一把 −0.581% 拆成 −0.321%（激励）+ −0.261%（传递函数），并解释为什么用比值能抵消前者。
2. 阶段二发现"无源级联有加载效应"，指出忽略 `R1C2` 项会算出 0.9198（偏高 1.50%），
   并用实测 −34.29° 站在含加载的 −34.19° 一边，反证 C1 确实挂在 mid 上。
3. 阶段三没有停在"报错了"，而是把 `H = K·1/(1+jω(R1∥R2)C)` 拆成两个可测因子去验证。

---

## 7. 这一轮挖出来的问题（以及 v0.8.0 怎么修的）

验收用的是 v0.7.0，**一行 API 没改**。问题在验收之后修，修完用真机回归。

### 7.1 问题清单

| # | 问题 | 谁发现的 | 严重度 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | `measure` 的 `gain` / `phase_deg` 按**探针添加顺序**配对，不看拓扑。先加输出探针 → `gain = 1/真值`、相位反号，而 `mode="ratio"` 看起来很权威 | 阶段二 + 阶段三（3 次独立复现） | **严重** | ✅ 已修 |
| 2 | `simulate.start` **传了不报错、也不生效**，波形仍从 t=0 开始 | 阶段一、二、三（都踩到） | 中 | ✅ 已修 |
| 3 | `get_waveform` 的 `preview` 用整数步长抽样，步长正好等于信号周期时每个点同相位，画出来是一条水平线 | 阶段二 | 轻（**数据本身没错**，是抽样方式会混叠） | ✅ 已改抽样方式 + 文档 |
| 4 | `topology.supported` 一个布尔值混了两件事："布局认不认"和"线接完没有" | 阶段一、三 | 中 | ✅ 新增 `complete` / `issues` |
| 5 | `mean`（全窗算术平均，含暂态）和 `offset`（拟合直流分量）语义容易混淆，差 4 个数量级 | 阶段一 | 轻 | ✅ 文档 |
| 6 | `add_component` 的 schema 没写各元件的 `pins` / `aliases`，只能"先加再看" | 阶段一、二 | 轻 | ✅ 文档 |
| 7 | `family` / `part` 用 `RESISTOR/RESISTOR_VIRTUAL` 斜杠写法列举，初读像一个字段 | 阶段一 | 轻 | ✅ 文档 |
| 8 | `connect` 给 `net` 时是"新建"还是"追加"没写清 | 阶段一 | 轻 | ✅ 文档（`created` 字段本来就有） |
| 9 | 返回的产物路径相对**仓库根**，不是相对 Agent 的 workdir | 阶段一 | 轻 | ✅ 文档 |
| 10 | 一阶 RC 低通的 `topology.kind` 叫 `bypass`（旁路），字面容易误解 | 阶段一 | 信息 | ⏸ 保留（改名会破坏已有文档/脚本），只在文档里说明 |
| 11 | 二阶电路 `measure.theory` 返回 `null` | 阶段二 | 信息 | ⏸ 设计如此：没有理论模型就不做数值判定，避免"自己和自己比" |

### 7.2 修法（只动会话层和 schema，不碰 `ir_sim` / `ir_compile` / `msbuild` / `mssafe`）

**问题 1 —— 按拓扑配对探针**（`circuit_session._pair_probes`）

```
输入探针 = 源正极所在网络上的探针
输出探针 = layout.analyze().out_net 上的探针
两个都找到 → pairing="topology"，gain = amp(out)/amp(in)
找不到     → 退回添加顺序，pairing="probe_order"，并在 notes 里明说"可能方向相反"
```

**问题 2 —— `start` 真的生效**

Multisim 的 COM 接口没有"从 t0 起算"的入口，所以仿真照旧从 0 跑，**导出窗口**裁掉
`t < start` 的采样点。schema 里写清"用它跳过启动暂态，不要指望它省计算时间"，
并加了 `start < 0` / `start >= stop` 的参数校验。

**问题 3 —— 预览改成非整数步长**：在整段窗口上均匀取 `max_points` 个点（含首尾），
采样相位逐点移动，不会再因为"步长 = 整数个周期"而画出水平线。

**问题 4 —— `supported` 与 `complete` 分开**

```json
"topology": {"kind": null, "supported": false, "reason": "parallel_shunt",
             "complete": true, "message": "网络 'out' 有 2 个到地元件…"}
```

`complete=true` 说明"电路接完了，是后端不会摆"；`complete=false` + `issues` 点名悬空引脚，
说明"你还有线没接"。Agent 不用再猜该改电路还是该换拓扑。

### 7.3 修复回归（真机，不是纯逻辑测试）

同一个 RC 拓扑（1 kΩ / 33 nF / 1 kHz），**故意先加输出探针**：

| 项 | v0.7.0（阶段二实测） | v0.8.0（回归） |
| --- | --- | --- |
| `in_probe` / `out_probe` | `P_out` / `P_in`（反） | **`P_in` / `P_out`** |
| `gain` | **1.104183**（= 1/0.9056） | **0.979043**（理论 0.979173，−0.013%） |
| `phase_deg` | **+34.29°**（符号反） | **−11.751°**（理论 −11.714°，−0.037°） |
| `pairing` | 不存在 | `topology` |
| `start=0.003, stop=0.007` | 返回 1400 点，t 从 0 开始 | **返回 800 点，t 从 0.003 开始** |
| `get_waveform(max_points=8)` | v 恒定 −0.508（混叠假象） | t = 0.003…0.007，v = −0.199, −0.227, 0.610, −0.877, 0.974, …（正弦） |

回归 trace：[`out/agent_v08/regress/trace.jsonl`](../out/agent_v08/regress/trace.jsonl)

**单元测试**：`test_mcp_session` **96 → 113 项**（新增 17 项覆盖配对 / `complete` / `start` 校验），
`test_layout` 51/51，全部通过。

---

## 8. 还没解决的

| 项 | 为什么先不解决 |
| --- | --- |
| `start` 不能省计算时间 | COM 没有"从 t0 起算"的入口；真要省得改 `ir_sim` 的调用方式并重新验证读数，风险大于收益 |
| `simulate` 20~30 s 阻塞，无 progress 通知 | 软 `timeout` 已能定位卡在哪一阶段；硬超时需要把 COM 挪到可 kill 的线程，属于重构 |
| `parallel_shunt` / `fork` 仍不支持 | P2.1 的范围（布局泛化），不是 Agent 层的问题 |
| 激励幅度 0.99679（−0.32%） | 从 v0.6.1 起就一直是这样，与负载无关，是读数/插值路径的固定标度。已文档化，但根因还没定位 |
| 产物路径相对仓库根 | 改成绝对路径会让 trace 不可移植；在 schema 里写清"相对仓库根"更划算 |

---

## 9. 结论

**问题一：一个外部 LLM 能不能只靠 MCP 语义工具完成"理解 → 设计 → 建模 → 仿真 → 测量 → 验算"？**

能。5 个任务、128 次调用、11 次真机仿真：

| 阶段 | 任务 | 调用 | 报错 | 结果 |
| --- | --- | --- | --- | --- |
| 一 | 一阶 RC，fc≈500 Hz | 15 | 0 | 增益误差 −0.261%，相位 −0.072° |
| 二 | 二阶 RC，fc≈2 kHz | 31 | 0 | 增益误差 −0.0594%，相位 −0.1025° |
| 三-1 | 缺参数注入 | 14 | 1 | 一次恢复，无重复 |
| 三-2 | 错误探针名 | 16 | 1 | 一次恢复，无重复 |
| 三-3 | 不支持的拓扑 | 52 | 1 | 识别边界 + 拆解验证，误差 1e-5 |

**3 次报错，3 次都在一次尝试内改对，0 次重复同类错误，0 次参数乱猜，0 个编造的数字。**

**问题二：v0.7.0 的 branch-aware layout 是不是真的能被 LLM 用上？**

是。阶段二的 Agent 自己选了 `R1-C1(mid)-R2-C2(out)` 的梯形，后端判定
`kind="ladder", n_series=2, n_shunt=2`，一次 `simulate` 跑通，误差 0.06%。
它甚至反过来用"加载项 `R1C2` 是否存在"来验证 C1 没被并到 out 上 —— 这说明它理解的是电路，
不是工具调用的顺序。

**问题三：这次验收最值钱的东西是什么？**

不是"通过了"，是**三个我们自己测不出来的缺陷**。脚本测试永远按自己设计的顺序调用，
所以"先加输入探针"这个隐含假设从来没被打破；LLM 不看你的脚本，它按自己的设计走，
于是把 `measure` 的配对 bug、`start` 的静默失效、`preview` 的抽样混叠一起踩了出来。

**一句话**：v0.7.0 证明"后端能跑二阶电路"，v0.8.0 证明"LLM 能自己把后端用起来"，
并且顺手把 API 表面最后一层不一致刮掉了。

---

## 10. 复现

```bash
# 0) 需要 32 位 Python（COM 限制）
runtime/py32/python.exe -c "import sys; print(sys.version, sys.maxsize > 2**32)"

# 1) 看 Agent 能看到的全部 API 文档
runtime/py32/python.exe tools/agent_acceptance/agent_cli.py \
    --workdir out/agent_v08/replay tools

# 2) 按 trace 复现阶段一（每行一条调用，args 原样照抄）
runtime/py32/python.exe tools/agent_acceptance/summarize.py \
    out/agent_v08/p1/trace.jsonl

# 3) 独立复算（防"measure 是编的"）
runtime/py32/python.exe tools/agent_acceptance/verify_sim.py \
    --trace out/agent_v08/p1/trace.jsonl --sim s-22aa89a47f

# 4) 跑单元测试
runtime/py32/python.exe tools/test_mcp_session.py    # 113 项
runtime/py32/python.exe tools/test_layout.py         # 51 项
```

> trace 里的 `circuit_id` / `sim_id` 属于**那一次运行**的会话目录，`out/mcp/sessions/`
> 不入库（体积大、可重跑）。要看当时的波形，用各阶段 `evidence/waveform.csv`。

---

## 11. 产物清单

| 文件 | 内容 |
| --- | --- |
| `out/agent_v08/p1/report.md` | 阶段一 Agent 的完整工程报告（13 项） |
| `out/agent_v08/p1/trace.jsonl` | 15 次调用的完整 args + result |
| `out/agent_v08/p1/calls.md` | 调用序列表格 + 统计 |
| `out/agent_v08/p1/verify_s22aa89a47f.json` | 独立复算（差值 0） |
| `out/agent_v08/p1/evidence/waveform.csv` | 2400 点原始波形 |
| `out/agent_v08/p2/report.md` | 阶段二报告（含 fc 定义、加载效应、Q 上限） |
| `out/agent_v08/p2/trace.jsonl` | 31 次调用 |
| `out/agent_v08/p2/verify_s29160bf3e9.json` | 独立复算（差值 0） |
| `out/agent_v08/p2/evidence/waveform.csv` | 1600 点原始波形 |
| `out/agent_v08/p3a/` | 缺参数注入：trace + 报错原文 + 报告 |
| `out/agent_v08/p3a_control/` | 同任务不注入的对照组（0 报错） |
| `out/agent_v08/p3b/` | 错误探针名：trace + 报错原文 + 报告 |
| `out/agent_v08/p3c/` | 不支持拓扑：trace + 4 次仿真的拆解验证 |
| `out/agent_v08/regress/` | v0.8.0 修复后的真机回归 |
| `tools/agent_acceptance/` | 测试台（4 个文件 + README） |
