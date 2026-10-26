# Agent Acceptance Test：一句设计需求 → 真实 Multisim 仿真

> **题目**
>
> 创建一个 1V、1kHz 的正弦输入，设计一个截止频率约为 500Hz 的一阶 RC 低通滤波器。
> 请自行选择合适的电阻和电容值，创建 Multisim 电路，进行瞬态仿真，
> 并告诉我输出端的实际幅值、理论幅值以及误差。

| | |
| --- | --- |
| **测试者** | 一个只读过 MCP `tools/list`、完全不了解 Multisim 内部概念的外部 Agent |
| **被测对象** | `multisim-circuit` MCP Server v0.6.0，7 个工具 |
| **硬约束** | 全程只走 MCP 协议：没 import 项目任何模块、没调 `msbuild`、没构造 Circuit IR、没碰 `.ms14` |
| **结果** | **13 次工具调用，零错误，一次通过** |

这不是"代码能跑"的演示。要回答的问题是：

> 一个**只知道工具语义、不知道 Multisim 内部**的 Agent，
> 能不能自己设计、自己建模、自己仿真、自己验算一个真实电路？

答案是可以，而且它自己算出来的数和理论值对得上。

---

## 一、Agent 自己做的设计决策

`fc = 1/(2πRC) = 500 Hz` 有无穷多组解。Agent 按 **E12 标准值**选：

| | 值 | 理由 |
| --- | --- | --- |
| R | 10 kΩ | E12 标准值；10k 量级让源内阻影响可忽略 |
| C | 33 nF | E12 标准值 |
| → fc | **482.288 Hz** | 距目标 500 Hz 偏 −3.5% |

它**没有**为了凑出 500.0 Hz 去用非标准值（31.83 nF）。真实设计选标准件，
偏差如实报告而不是掩盖 —— 这个选择是 Agent 自己做的，不是脚本里写死的。

---

## 二、电路

**Multisim 的真实输出，原样贴上来，没裁剪没重绘：**

![Multisim 截图](https://raw.githubusercontent.com/A3-77/multisim-14.3-ai-automation/main/docs/case/agent_rc_500hz_multisim_render.png)

R1 和两个探针画出来了，**V1 和 C1 的符号是空的**。
这是 Multisim `GetCircuitImage` 对我们生成的 `.ms14` 的渲染缺陷，
不是电路接错了 —— 仿真照跑、读数照对（见下面问题 8）。

> 如果只想看接法，附一张按同一份会话数据画的结构图（**可选项，默认不生成**）：

![电路结构（可选，按会话数据重绘）](https://raw.githubusercontent.com/A3-77/multisim-14.3-ai-automation/main/docs/case/agent_rc_500hz_circuit.png)

从这张图能看出几件事：

- Agent **没有指定任何坐标**。它只说"V1 的 `+` 接 R1 的 `1`"，
  布局、走线、探针几何全部由后端完成
- 网络名 `in` / `n1` / `0` 是后端自动命名的，不是 Agent 起的
- 探针 `P1` 落在输入网 `in`，`P2` 落在 RC 中点 `n1`

---

## 三、波形（真实采样点）

![波形](https://raw.githubusercontent.com/A3-77/multisim-14.3-ai-automation/main/docs/case/agent_rc_500hz_waveform.png)

数据来自 `out/mcp/sessions/c-eccf480d70/sims/s-042f992be7.csv` ——
`simulate` 从 Multisim COM 读回来的**原始 1200 个采样点**，没有重采样、没有插值、没有平滑。

两件事能证明这是真的电路：

1. 起始段输出明显滞后（电容充电暂态），稳态段是干净的 1 kHz 正弦
2. 输出滞后输入约 **64°**，幅值是输入的 **43%** —— 正是 fc=482 Hz 在 1 kHz 处的响应

如果电容被短路、或探针接错网，输出会和输入同相且等幅。实际不是。

---

## 四、实测 vs 理论

| 项 | 实测 | 理论 | 误差 |
| --- | --- | --- | --- |
| 输入幅值 | **0.996791 V** | 1.000000 V | −0.32% |
| 输出幅值 | **0.431897 V** | 0.434405 V | **−0.577%** |
| 增益 | **0.433288** | 0.434405 | −0.257%（相对） |
| 相位 | **−64.327°** | −64.253° | **−0.074°** |
| fc | 482.288 Hz | 目标 500 Hz | −3.5%（设计选择，不是仿真误差） |

**结论：符合一阶 RC 低通理论。** 幅值误差 0.58%、相位误差 0.07°。

要区分两个"误差"：

- **−3.5% 是设计偏差** —— 选了标准件 33 nF 而不是 31.83 nF
- **−0.58% 是仿真/测量误差** —— 这才是 MCP 链路的质量指标

---

## 五、Agent 调用的 13 次工具（零错误）

```
create_circuit(name="agent_rc_500hz")                              -> c-eccf480d70
add_component(SIGNAL_VOLTAGE_SOURCES, AC_VOLTAGE, V1, value=1.0, frequency=1000.0)
add_component(RESISTOR,   RESISTOR_VIRTUAL,   R1, value=10000.0)
add_component(CAPACITOR,  CAPACITOR_VIRTUAL,  C1, value=33e-9)
add_component(POWER_SOURCES, GROUND, GND1)
connect(pins=[["V1","+"], ["R1","1"]])               -> 自动命名 "in"
connect(pins=[["R1","2"], ["C1","1"]])               -> 自动命名 "n1"
connect(pins=[["C1","2"], ["V1","-"], ["GND1","1"]]) -> 自动命名 "0"
add_probe(target="in")                               -> P1 @ in
add_probe(target="R1.2")                             -> P2 @ n1
simulate(analysis="transient")                       -> s-042f992be7  (29.7 s)
measure(sim_id=...)                                  -> gain / phase / channels
get_waveform(sim_id=..., max_points=20)              -> 摘要 + artifact
```

**主任务 13 次调用，没有一次报错，没有一次重试。**

---

## 六、为什么可以确定 Multisim 真的跑了

| 证据 | 内容 |
| --- | --- |
| 服务端启动日志 | `[mcp] multisim-circuit v0.6.0 就绪（python 3.11.9, 32 位）` |
| `simulate` 耗时 | **29.7 s**（编译 + 启 Multisim + 跑仿真 + 读数；纯计算不会这么慢） |
| 输出名 | `['V(探针1)', 'V(探针2)']` —— 这是 COM `EnumOutputs` 的命名，不是 IR 里的 `P1/P2` |
| `.ms14` 产物 | `agent_rc_500hz.ms14`，**31 799 字节**（真实文件，不是桩） |
| 波形 CSV | **1201 行**（1200 采样点 + 表头），起始段有电容充电暂态 |
| **独立复算** | Agent 用纯标准库自己写了最小二乘，从 CSV 复算出 gain **0.433288**、phase **−64.327°**，与 `measure` **完全一致** |

最后一条是关键：**如果 `measure` 是编出来的数，从原始波形不可能复算出同一个值。**

---

## 七、这次测试暴露的问题（只提问题，没改任何代码）

按严重程度排序，完整描述见
[`out/agent_test/AGENT_ACCEPTANCE_REPORT.md`](https://github.com/A3-77/multisim-14.3-ai-automation/blob/main/out/agent_test/AGENT_ACCEPTANCE_REPORT.md)。

| # | 问题 | 严重度 |
| --- | --- | --- |
| 1 | `measure` 与 `get_waveform` 的 `channels` 用不同 key（`P1` vs `V(探针1)`），Agent 必须自己做映射 | 严重 |
| 2 | `get_waveform` 的 `probe` 参数描述写"输出名"，实际只接受探针名 `P1` | 中 |
| 3 | `context` 结构不统一：`supported` 是数组，`available` 是嵌套对象 | 轻 |
| 4 | 没有 `get_circuit`，跨会话/重启后查不到已有电路状态，只能重建 | 中 |
| 5 | `simulate` 阻塞且无 progress / timeout 参数，本次 29.7 s，接近常见 60 s 超时 | 中 |
| 6 | `add_component` 的 `params` 泄漏了 Multisim 的"参数序号"概念 | 轻 |
| 7 | 拓扑硬墙（并联 / >2 个无源元件）在 `connect` 阶段无预警，建完才在 `simulate` 被拒 | 信息 |
| 8 | Multisim `GetCircuitImage` 对我们生成的 `.ms14` **画不出 V1/C1 符号** | 中 |

### 问题 8 的证据

就是上面「二、电路」那张图：R1 和两个探针画出来了，**V1 和 C1 的符号是空的**，只剩导线框架。

排查结论（细节见报告）：不是时序问题（立即导出与等 4 s 字节数相同）、
不是 XML 缺元素（4 个 `CIITSymbolComp` 都有 `Objects` 子节点）、
不是文件不被接受（仿真照跑、读数照对）、
让 Multisim 自己 `save_as` 再 reopen 后导出一样缺。
**而 Multisim 自带样例渲染完整** —— 所以这是"我们生成的 `.ms14`"特有的问题，不是 API 限制。

**不影响仿真正确性**（仿真走网表，不走图形），但影响"给人看"：
一份生成的电路如果连原理图都画不出来，用户没法目视核对接法。

---

## 八、Agent 给出的判断

> **7 个工具的语义边界清楚，`tools/list` 的 description 足以在完全不读源码的情况下
> 决定每次传什么参数。坐标完全不用管 —— 我全程没想过"元件放哪"。
> 错误信息 9/9 都能指导恢复，`hint` 是真能执行的动作，不是"操作失败"。**
>
> **但问题 1/2/3 是同一种病：命名和结构不一致。** 不影响我完成本次任务（因为我读 description），
> 但会影响一个不读 description、只看字段名的 LLM。一旦接上 LLM，
> 这些不一致会变成"Agent 随机写错代码"，而且很难从日志里看出是 API 的问题还是模型的问题。

它建议的下一步是 **A（修 MCP API 的一致性）**，而不是直接进 P2 或接 LLM ——
理由：问题 1/2/3 修改成本极低（只改字段名和描述），收益很高；
问题 4/5 是接 LLM 前必须解决的（多轮对话一定会遇到"我上次建的电路呢"）；
而这些修改**不动任何核心机制**（不碰 `ir_sim` / `ir_compile` / `msbuild` / `mssafe`）。

---

## 九、复现

```bash
# 1) 需要 32 位 Python（COM 限制）
runtime/py32/python.exe out/agent_test/run_task.py

# 2) 会话产物
out/mcp/sessions/c-eccf480d70/
├── circuit.ir.json                # 电路（元件/网络/探针）
├── agent_rc_500hz.ms14            # 生成的 Multisim 文件（31 799 字节）
├── agent_rc_500hz.compile.json    # 编译记录（donor、ciid、探针坐标）
└── sims/
    ├── s-042f992be7.csv           # 1200 个原始采样点
    └── s-042f992be7.json          # 仿真元数据 + 摘要
```

## 附：本次测试的产物

| 文件 | 内容 |
| --- | --- |
| `out/agent_test/run_task.py` | 任务脚本（外部 Agent 视角） |
| `out/agent_test/mcp_client_min.py` | Agent 自己写的最小 MCP 客户端（只用标准库） |
| `out/agent_test/trace.json` | 17 次调用的完整轨迹 |
| `out/agent_test/probe_api.py` | 8 组 API 边界探测 |
| `out/agent_test/api_probe.json` | 探测结果 |
| `out/agent_test/AGENT_ACCEPTANCE_REPORT.md` | 完整验收报告（11 项） |
| `out/agent_test/make_circuit_shot2.py` | 从会话数据画电路结构图 |
| `out/agent_test/make_wave_shot.py` | 从原始 CSV 画波形图 |
