# MCP Tool API —— 电路执行器

> 版本：**v0.7.0**（v0.6.0 首版 → v0.6.1 Agent 验收 → v0.6.2 接口一致性修整 → v0.7.0 分支感知布局）
> 定位：把已经验证过的 **Circuit IR + Multisim 执行链**包成一个 Agent 能直接用的接口。
> 代码：`tools/circuit_session.py`（业务逻辑）+ `tools/mcp_server.py`（协议层）。
>
> v0.6.2 只做了一件事：**把 API 表面上的不一致清干净**。
> 起因是一次外部 Agent 验收（见 `out/agent_test/AGENT_ACCEPTANCE_REPORT.md`）——
> 主流程 13 次调用零错误，但暴露出 3 处"同一个概念两套命名"。
> 这一版不碰 `ir_sim` / `ir_compile` / `msbuild` / `mssafe`，只改返回结构和 schema 文案。
>
> **v0.7.0（P2）**：布局从『单链』升级成『先判断拓扑、再生成坐标』，
> 支持单主干 + 到地并联支路（分压 / 旁路电容 / T 型 / 多级 RC 梯形）。
> 新增 `tools/layout.py`；`circuit_session` 里不再有拓扑逻辑。
> 详见 [layout.md](layout.md)。

---

## 1. 它不是"把 Python 函数套一层 MCP"

这是这一版最重要的设计决定。`nl_run.py` 那种"一句话跑到底"的脚本，
外面套个 MCP 壳也能用，但 Agent 只能整条调，没法一步步改电路、看中间状态。

所以这一版分了严格的两层：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 协议层 | `mcp_server.py` | JSON-RPC over stdio、tools/list、tools/call。**只做收发** |
| 会话层 | `circuit_session.py` | 电路句柄、语义参数映射、唯一性检查、自动命名、**自动布局**、分析类型匹配、结构化错误 |

会话层有真业务逻辑，所以它能单独测试（`test_mcp_session.py` 96 项 +
`test_layout.py` 51 项，都不需要 Multisim）。
协议层薄到没有分支逻辑，坏了很容易看出来。

---

## 2. 状态模型：Agent 不需要每次重新描述整个电路

```
create_circuit  ──►  circuit_id
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   add_component     connect         add_probe      （可任意顺序、多次）
        └────────────────┼────────────────┘
                         ▼
                     simulate  ──►  sim_id
                         │
                ┌────────┴────────┐
                ▼                 ▼
             measure         get_waveform
```

`circuit_id` 映射到磁盘目录 `out/mcp/sessions/<circuit_id>/`：

```
circuit.ir.json      当前 Circuit IR（纯 JSON，可 diff、可手工改）
session.json         元信息 + 仿真历史
sims/s-xxxxxxxxxx.json   一次仿真的记录（输出名、探针映射、RLC、摘要）
sims/s-xxxxxxxxxx.csv    波形
sims/s-xxxxxxxxxx.ir.json  那次仿真用的 IR 快照
```

**服务是无状态的**：每个调用都从磁盘读、改、写回。进程重启不丢电路。
每次 `add_component` / `connect` / `add_probe` 都返回完整状态快照，
所以 Agent 随时知道电路长什么样，不需要额外的 `get_circuit`。

---

## 3. 八个工具

### `create_circuit`

| 输入 | 输出 |
| --- | --- |
| `name?` | `circuit_id`、空列表、`counts` |

不立刻生成 `.ms14`。编译发生在 `simulate` —— 因为布局要等拓扑定下来才能算。

### `add_component`

```json
{"circuit_id": "c-...", "family": "RESISTOR", "part": "RESISTOR_VIRTUAL",
 "refdes": "R1", "value": 1000}
```

**参数是语义的，不是 Multisim 的。** 对比一下：

| 元件 | Agent 传的 | 落到 IR 的 |
| --- | --- | --- |
| `AC_VOLTAGE` | `value=1.0, parameters={"frequency": 1000}` | `value=1.0, params={5: 1000.0}` |
| `DC_POWER` | `value=5.0` | `value=5.0, params={}` |
| `RESISTOR_VIRTUAL` | `value=1000` | `value=1000.0` |
| `CAPACITOR_VIRTUAL` | `value=159e-9` | `value=1.59e-07` |
| `GROUND` | （不给） | `value=None` |

`params={5: 1000}` 里的 `5` 是 Multisim 的参数序号。**它在 MCP 边界上完全不存在**：

| 情况 | 结果 |
| --- | --- |
| `parameters={"frequency": 1000}` | 正常 |
| `frequency=1000`（便捷写法，等价） | 正常 |
| `parameters={"frequency": 1000}` + `frequency=2000` | `BAD_ARGUMENT` —— 不猜以哪个为准 |
| `parameters={"freq": 1000}` | `UNKNOWN_PARAMETER`，`context.supported` 列出可用参数 |
| `params={"5": 1000}`（v0.6.0 的旧写法） | `UNSUPPORTED_PARAMETER`，hint 指向 `parameters` |

返回的 `component` 是**固定 9 字段**，不会因为元件类型少字段：

```json
{"refdes": "V1", "family": "SIGNAL_VOLTAGE_SOURCES", "part": "AC_VOLTAGE",
 "value": 1.0, "value_name": "amplitude", "value_unit": "V",
 "parameters": {"frequency": 1000.0},
 "pins": ["1", "2"], "aliases": {"+": "1", "-": "2"}}
```

`value_name` / `value_unit` 说明 `value` 到底是什么（幅值？阻值？容值？），
不用 Agent 记。没有附加参数时 `parameters` 是 `{}` 而不是缺字段。

第一版只开放这五种（都跑通过真机仿真）。传电感会得到
`UNKNOWN_COMPONENT_TYPE` 并列出可用类型。

`refdes` 不传就自动编号（`R1`、`R2`…，按 family 前缀）。

### `connect`

```json
{"circuit_id": "c-...", "pins": [["V1","+"], ["R1","1"]]}
{"circuit_id": "c-...", "pins": ["R1.2", "C1.1"]}
{"circuit_id": "c-...", "pins": [["C1","2"], ["GND1","1"]], "net": "0"}
```

**不要传坐标。** 坐标由 `simulate` 时的 `plan_layout()` 算。

网络名可以不给，规则是：

| 情况 | 自动命名 |
| --- | --- |
| 引脚里有 GROUND | `0` |
| 引脚里有电源正极 | `in` |
| 其它 | `n1`、`n2`… |

也可以显式给 `net` 把引脚**追加**到已有网络 —— 这样 Agent 可以一条边一条边地描述：

```
connect([["V1","+"], ["R1","1"]])            -> 新建 "in"
connect([["R1","2"], ["C1","1"]])            -> 新建 "n1"
connect([["C1","2"], ["GND1","1"]], "0")     -> 新建 "0"
connect([["V1","-"]], "0")                   -> 追加到 "0"
```

不给 `net` 时如果这些引脚已经全在同一个网络里，会**复用**那个网络（幂等）。
分属不同网络则报 `PIN_ALREADY_CONNECTED` —— 不猜要不要合并。

### `add_probe`

```json
{"circuit_id": "c-...", "target": "in"}
{"circuit_id": "c-...", "target": "R1.2"}
```

`target` 可以是网络名，也可以是引脚（自动解析成它所在的网络）。
传元件位号（`"R1"`）会得到 `AMBIGUOUS_TARGET`，因为两端元件有两个引脚。

MCP 自己处理 `LocalName`、几何落点、唯一命名、序号分配。
上限 **9 个**（序号超过一位数字的命名规则没验证），第 10 个报 `PROBE_LIMIT`。

**探针只有 `probe_id` 一个身份**（就是 `name` 给的那个，默认 `P1`）。
`label`（`探针1`）和 `output`（`V(探针1)`）是 Multisim 那边的只读旁证，
只出现在返回里，**永远不用来传参**。

### `get_circuit`

```json
{"circuit_id": "c-..."}
```

只读，什么都不改。返回和 `create_circuit` / `add_component` / `connect` **完全相同**的快照结构。

用途不是"跨会话兜底"这么窄 —— 复杂任务里 Agent 非常需要一句"我刚才到底搭成什么样了"：
改完一轮核对、隔了几轮对话只记得 `circuit_id`、动手前先看看已经有什么。
返回里带 `simulations` 列表，所以也能看到"这个电路跑过几次、每次是什么分析"。

如果这个电路仿真过，`probes[]` 里的 `label` / `output` 会被填上（否则是 `null`）——
从最近一次仿真记录里读，不需要重跑。

### `simulate`

```json
{"circuit_id": "c-...", "analysis": "transient"}
{"circuit_id": "c-...", "analysis": "dc"}
```

内部依次做：算仿真参数 → `validate()` → **拓扑判断 + 布局** → 写回 IR → 编译 `.ms14` → 开 Multisim → 读探针 → 落盘。
（`validate()` 排在拓扑之前，这样"元件没接线"报的是具体引脚，而不是被拓扑层笼统判成 `island`。）

**分析类型和源类型是强制的，不会为了接口统一而放宽**：

| 源 | 允许的分析 | 默认 |
| --- | --- | --- |
| `AC_VOLTAGE` | `transient` | `transient` |
| `DC_POWER` | `dc`、`transient` | `dc` |

`AC_VOLTAGE` + `dc` 会得到：

```json
{"ok": false, "error": {
  "code": "ANALYSIS_NOT_SUPPORTED",
  "message": "AC_VOLTAGE 不支持 dc（当前后端只验证过 transient）",
  "hint": "把 analysis 改成 'transient'，或者把源换成支持 'dc' 的类型。",
  "context": {"analysis": "dc", "source_part": "AC_VOLTAGE",
              "source_refdes": "V1", "supported": ["transient"]}}}
```

`transient` 不传 `stop` / `sample_rate` 时按信号频率推算：6 个周期、每周期 200 点
（和 `nl2ir` 的默认值一致，这个组合在真机上验证过）。

返回里带 `sim_id`、`outputs`、`probes`、`summary`（按 probe_id 键）、`record`、
`waveform`、`timing`。

**`timing` 是 v0.6.2 新加的**，因为 `simulate` 是阻塞的、实测单次 30 s 左右：

```json
"timing": {"layout_s": 0.001, "compile_s": 0.42, "run_s": 31.6, "total_s": 32.1}
```

Agent 拿到这个数就能判断"这个电路该给多少超时"，而不是靠猜。

`timeout`（秒）是**软超时**：只在阶段之间（布局 / 编译 / 跑仿真）检查，
**无法中断已经在进行的 Multisim COM 调用**。超了返回 `SIMULATION_TIMEOUT`，
带上 `phase` 和 `elapsed_s`。把它写成硬超时需要把 COM 调用挪到可 kill 的线程里，
属于重构 —— 等复杂电路真的把时间压到边界上再说。

> ⚠️ **`EnumOutputs` 只在 open 后调一次**这条铁律封在 `ir_sim` 里，Agent 碰不到。
> 见 [dc-static.md](dc-static.md)。

### `measure`

```json
{"sim_id": "s-...", "what": "all"}
{"sim_id": "s-...", "what": "amplitude", "probe_id": "P2"}
```

| `what` | 返回 |
| --- | --- |
| `all`（默认） | 全部 |
| `voltage` | 每通道 `mean / rms / min / max` |
| `amplitude` | 每通道正弦拟合幅值（仅 transient） |
| `phase` | 每通道相位（仅 transient） |
| `dc_voltage` | 每通道直流电压（仅 dc） |

`transient` 额外给 `gain`、`phase_deg`、`theory`；`dc` 给 `v_resistor`、`current`。

`channels` 是**以 `probe_id` 为键**的对象，和 `get_waveform` 的 `channels` 完全一致。
每个通道固定带 `probe_id` / `label` / `output` / `net` / `kind`，再叠加测量字段。
**`what` 过滤不会删掉身份字段** —— 否则 `what="amplitude"` 之后 Agent 就不知道
这个通道是哪个探针了。

**拟合算法没有重写**，直接调 `ir_sim.fit_channels()`（最小二乘）。
`dc` 的电流仍是 `I = V_R / R`，`R` 是 **Multisim 读回来的实际阻值**（不是从 IR 抄的），
返回里用 `r_source` 标明来源（`multisim` / `ir`），不假装用了电流探针。

`measure` 按**拓扑**找源网和地网，不依赖网络叫什么名字 —— 所以 Agent 把
网络命名成 `vcc` / `gnd` 也能正确算出电阻电压。

### `get_waveform`

```json
{"sim_id": "s-...", "probe_id": "P1", "max_points": 200}
```

不会把整条波形塞进返回值。默认给摘要（`n` / `min` / `max` / `mean` / `t_range`）
+ 最多 `max_points` 个采样点的预览（均匀抽样），完整数据在 `artifact` 指向的 CSV。

`channels` 和 `measure` 用同一套键（`probe_id`），两个工具的结果可以直接对照。

> v0.6.0/v0.6.1 这里写的是 `probe`，描述还写成"输出名"，
> 结果 Agent 传 `V(探针1)` 会失败 —— 这是 v0.6.1 验收里实际踩到的坑。
> v0.6.2 改成 `probe_id`，并且**传错会明确告诉你该传什么**：
>
> ```json
> {"code": "PROBE_NOT_FOUND",
>  "message": "'V(探针1)' 是 Multisim 那边的名字，不是 probe_id",
>  "hint": "probe_id 是 'P1'。measure / get_waveform 只接受 probe_id；"
>          "label / output 是只读旁证，不要拿它传参。",
>  "context": {"field": "probe_id", "value": "V(探针1)",
>              "available": ["P1", "P2"], "matched": "P1"}}
> ```

---

## 4. 统一的返回对象（v0.6.2 的修整）

v0.6.1 的验收报告里，问题 1/2/3 是**同一种病**：同一个概念，两个工具给两种形状。
Agent 写通用代码时只能每次特殊处理；一旦接上 LLM，这种不一致会变成
"模型随机写错代码"，而且事后无法判断是 API 的问题还是模型的问题。

所以 v0.6.2 把返回对象收敛成 4 个固定形状。**字段固定，不因类型而少字段** ——
没有的值是 `null` / `{}` / `[]`，而不是字段消失。

### 4.1 `component`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `refdes` | str | 位号 |
| `family` / `part` | str | 元件类型 |
| `value` | number\|null | 主值（地是 `null`） |
| `value_name` | str\|null | 这个值**是什么**：`amplitude` / `voltage` / `resistance` / `capacitance` |
| `value_unit` | str\|null | 单位：`V` / `ohm` / `F` |
| `parameters` | object | 语义参数，`{}` 或 `{"frequency": 1000.0}` |
| `pins` | str[] | 实际引脚名 |
| `aliases` | object | 别名映射 `{"+": "1", "-": "2"}` |

### 4.2 `probe` / `channel` —— 同一个形状

`probes[]`（`simulate` / `get_circuit` / `measure` / `get_waveform`）
和 `channels{}` 里的每一项都用它：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `probe_id` | str | **唯一语义 ID**，Agent 传参只认它 |
| `label` | str\|null | Multisim 显示名（`探针1`），只读旁证 |
| `output` | str\|null | COM 输出名（`V(探针1)`），只读旁证 |
| `net` | str | 所在网络 |
| `kind` | str | 目前只有 `V`（电压探针） |

`channels` 是 **`{probe_id: channel}`**，`measure` 和 `get_waveform` 完全一致 ——
两个工具的结果可以直接对照，不需要 Agent 自己建映射表。

`label` / `output` 在 `simulate` 之前是 `null`（那时还没有 COM 输出名），
但**字段一直在**，所以 Agent 的取值代码不用写 `if "label" in ch`。

### 4.3 `net`

`{name, pins}`。`connect` 额外在**顶层**给一个 `created` 布尔值（是不是新建的），
不塞进 `net` 里 —— 这样 `net` 在所有工具里形状一致。

### 4.4 错误的 `context`

字段名和类型固定，Agent 可以写一份通用错误处理器：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `field` | str | 出问题的参数名 |
| `value` | any | 传进来的值 |
| `supported` | str[] | 这个参数**能**取什么 |
| `available` | str[] | 当前**可用**什么 |
| `existing` | str[] | 已经存在的名字 |
| `pins` / `nets` | str[] | 涉及的引脚（`R1.2`）/ 网络 |
| `aliases` | object | 别名映射 |
| `issues` | object[] | `validate()` 的问题列表 |
| `refdes` / `pin` / `net` / `part` / `family` / `analysis` / `phase` | str | 定位 |
| `count` / `limit` / `elapsed_s` / `timeout_s` | number | 数量与耗时 |

规则只有一条：**同一个字段名，永远是同一个类型。**

v0.6.1 反例（已修）：

```json
// UNKNOWN_COMPONENT_TYPE：supported 是数组
"context": {"supported": ["SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE", ...]}

// PIN_NOT_FOUND：available 却是嵌套对象
"context": {"available": {"pins": ["1","2"], "aliases": {"+":"1"}}}
```

现在 `PIN_NOT_FOUND` 是：

```json
"context": {"refdes": "R1", "pin": "9",
            "available": ["1", "2"], "aliases": {"+": "1", "-": "2"}}
```

---

## 5. 数据模型：MCP 层不暴露什么

`tools_schema.json` 里做过一条自动检查：**不出现** `CiID` / `CiPort` /
`CIITSymbolComp` / `SimState`。

Agent 能看到的只有：

```
circuit_id
component   { refdes, family, part, value, value_name, value_unit,
              parameters, pins, aliases }
net         { name, pins[] }
probe       { probe_id, label, output, net, kind }
channel     { probe_id, label, output, net, kind, ...测量字段 }
simulation  { analysis, start, stop, sample_rate }
```

没有 donor 文件、没有坐标、没有 XML ID、没有参数序号。

`label` / `output` 是 v0.6.2 里唯一带 Multisim 味道的字段，但它们**只读、只用来对照**，
不参与寻址 —— 传参一律用 `probe_id`。这样 Agent 在 Multisim 界面上核对结果时有个抓手，
又不会被迫理解 `EnumOutputs` 那套命名。

---

## 6. 自动布局：坐标归底层管

`plan_layout()` 在 `simulate` 时按拓扑算坐标。**Agent 永远不用给坐标。**

v0.7.0（P2）起，布局分成两步，**拓扑判断先于坐标布局**：

```
Circuit IR → layout.analyze() → Topology → layout.plan() → {refdes: [x, y]}
```

`analyze()` 不认识坐标，`plan()` 不认识电路语义。完整设计、支持的拓扑类、
拒绝规则、以及一次真实的几何 bug 都记在 [layout.md](layout.md)。

### 6.1 支持的拓扑：单主干 + 到地并联支路

| kind | 结构 | 例子 |
| --- | --- | --- |
| `shunt_load` | 0 串联 + 1 到地 | 直流 5 V + 1 kΩ |
| `series_chain` | N 串联 + 0 到地 | 空载串联 |
| `divider` | 1 串联 + 1 到地（电阻） | 电阻分压 |
| `bypass` | 1 串联 + 1 到地（电容） | 一阶 RC 低通 |
| `tee` | 2 串联 + 1 到地（电阻，中间级） | T 型网络 |
| `ladder` | 其它（≥2 串联，≥1 到地） | 二阶 RC 梯形 |

每级最多一个到地元件；主干最多 4 级。

### 6.2 坐标网格

| 位置 | 坐标 |
| --- | --- |
| 电源 | `(300, 300)` —— 独占最左列 |
| 第 i 级的列 | `x = 540 + 240*i` |
| 第 i 级串联元件 | `(x + 120, 300)` |
| 第 i 级到地元件 | `(x, 460)` |
| 地 | `(300, 620)` |

> 电源必须独占最左列。第 0 级如果放在 `x = 300`（电源正下方），
> 到地元件回电源负极的导线会**横穿自己的符号框**，Multisim 会少认一个
> 探针通道（表现为"仿真成功但只有一个通道有数"）。细节见 layout.md 第 6 节。

### 6.3 拓扑不在支持范围内时

明确报错，不硬排：

```json
{"code": "LAYOUT_UNSUPPORTED",
 "message": "网络 'in' 有 2 个到地元件（R1, R2），是并联到地",
 "hint": "P2 每一级最多一个到地元件。两个元件并联到地（比如电阻和电容并联）还没验证过；拆成一个元件，或先用两个电路分别验。",
 "context": {"reason": "parallel_shunt", "net": "in", "shunts": ["R1", "R2"]}}
```

`context.reason` 是机器可读的分类：`fork` / `parallel_shunt` / `island` /
`open_pin` / `cycle` / `too_many_stages`。

### 6.4 电路还没搭完也能看拓扑

每个状态快照（`create` / `add_component` / `connect` / `add_probe` /
`get_circuit`）都带 `topology`。电路还不完整时不是报错，而是：

```json
{"kind": null, "supported": false, "reason": "island",
 "message": "这些元件和电源不连通（R2）",
 "hint": "P2 只支持从电源正极一路走到地的连通拓扑。..."}
```

这样 Agent 可以在 `simulate` 之前就知道后端会怎么理解它的电路。

---

## 7. 错误设计

每个错误都是 `{code, message, hint, context}`。`hint` 是**可执行**的建议，
`context` 是机器可读的上下文 —— LLM 接进来之后能靠这两样自己纠正。

| code | 什么时候 | hint 说什么 |
| --- | --- | --- |
| `UNKNOWN_COMPONENT_TYPE` | 元件不在白名单 | 列出 5 种可用类型 |
| `MISSING_VALUE` | 电阻/电容/源缺值 | 该传哪个字段 |
| `MISSING_PARAMETER` | `AC_VOLTAGE` 缺 `frequency` | 传 `frequency=<数值>` |
| `DUPLICATE_REFDES` | 位号重复 | 换位号或不传（自动编号） |
| `PIN_NOT_FOUND` | 引脚不存在 | 列出该元件实际引脚 |
| `PIN_ALREADY_CONNECTED` | 一个引脚两条网络 | 说明为什么不能合并 |
| `COMPONENT_NOT_FOUND` | 引用不存在的元件 | 先 add_component |
| `NET_NOT_FOUND` | 目标网络不存在 | 列出可用网络 |
| `AMBIGUOUS_TARGET` | 探针目标给了元件位号 | 写成 `R1.1` / `R1.2` |
| `PROBE_LIMIT` | 超过 9 个探针 | 说明为什么是 9 |
| `PROBE_DUPLICATE` | 探针重名 | 换名字或不传 |
| `ANALYSIS_NOT_SUPPORTED` | 源和分析类型不匹配 | 该改成什么 |
| `NO_SOURCE` / `NO_GROUND` / `NO_PROBE` | 电路不完整 | 缺什么 |
| `LAYOUT_UNSUPPORTED` | 拓扑不在支持范围 | 说明支持哪几类，`context.reason` 给出分类 |
| `MULTIPLE_SOURCES` / `SOURCE_NOT_GROUNDED` | 单电源前提不成立 | 怎么改接法 |
| `VALIDATION_FAILED` | IR 校验不过 | 带 `issues` 列表，逐条修 |
| `COMPILE_FAILED` | IR → `.ms14` 失败 | 通常是布局/引脚映射 |
| `SIMULATION_FAILED` | Multisim 没返回数据 | 检查探针是否落在导线上 |

---

## 8. 验收（实测，真跑 Multisim）

`tools/mcp_client.py` 起 server 子进程，**走真实 MCP 协议**（不是直接调 Python 函数），
建两个电路：

### RC 低通（1 V / 1 kHz / 1 kΩ / 159 nF）

| 检查项 | 结果 |
| --- | --- |
| `create_circuit` | `c-a580bc84c8` |
| 三个 `connect` 的自动命名 | `in` / `n1` / `0` |
| 探针用引脚名指定 | `R1.2` → 自动解析到 `n1` |
| `simulate` 自动选分析类型 | `transient`，32.1 s（`timing.run_s`） |
| Multisim 注册输出 | `['V(探针1)', 'V(探针2)']` |
| **增益** | **0.706316**（`nl_run` 同电路 0.70632） |
| **相位** | **−45.065°**（`nl_run` −45.06°） |
| 与理论 \|H\|=0.70745 | Δ=0.00114 |
| 与理论 ∠H=−44.97° | Δ=0.093° |

### 直流（5 V / 1 kΩ 接地）

| 检查项 | 结果 |
| --- | --- |
| `DC_POWER` 默认分析 | `dc` |
| 每个探针的采样点 | 1（直流工作点） |
| `V(source)` / `V(ground)` | 5.000000 / 0.000000 |
| 电阻两端电压 | 5.000000 |
| `R` | 1000.0（`r_source="multisim"`，Multisim 读回值） |
| **电流** | **0.005000 A** |

### 错误路径

| 场景 | 错误码 |
| --- | --- |
| `AC_VOLTAGE` + `analysis="dc"` | `ANALYSIS_NOT_SUPPORTED`（带 `supported: ["transient"]`） |
| 并联到地 | `LAYOUT_UNSUPPORTED`（`reason="parallel_shunt"`、`shunts=["R1","R2"]`） |
| `add_probe(target="R1")` | `AMBIGUOUS_TARGET`（提示写成 `R1.1`） |
| 电感 | `UNKNOWN_COMPONENT_TYPE`（列出 5 种可用） |
| `AC_VOLTAGE` 缺 `frequency` | `MISSING_PARAMETER`（`context.field="frequency"`） |
| 跨网络硬连 | `PIN_ALREADY_CONNECTED` |

### v0.6.2 新增的一致性断言

| 检查项 | 结果 |
| --- | --- |
| `measure` 与 `get_waveform` 的 `channels` 键 | 都是 `['P1','P2']` |
| `what="amplitude"` 之后身份字段 | 仍在（`probe_id` / `label` / `output`） |
| `probe_id="P2"` 过滤 | 只剩 `P2` |
| 通道上的 Multisim 旁证 | `label=探针2`、`output=V(探针2)` |
| `get_circuit` 读回 | 4 元件 / 3 网络 / 2 探针 |
| 仿真后 `get_circuit` 的 `probes[].output` | `['V(探针1)','V(探针2)']`（不用重跑） |

### v0.7.0 新增（P2）

| 检查项 | 结果 |
| --- | --- |
| 并联到地报错 | `LAYOUT_UNSUPPORTED`，`context.reason = parallel_shunt`，`shunts = ['R1','R2']` |
| 直流两个探针 | `{'P1': 1, 'P2': 1}`，5.000000 V / 0.000000 V / 1000 Ω / 0.005000 A |
| 一阶 RC（新网格坐标） | 0.706316 / −45.065°，与旧网格逐位一致 |

**56 项断言全部通过**，结果落在 `out/mcp/acceptance.json`。

---

## 9. 怎么接 Agent

server 必须用 **32 位 Python**（COM 限制）：

```json
{
  "mcpServers": {
    "multisim-circuit": {
      "command": "C:/Users/<you>/WorkBuddy AI/ni/multisim-ctrl/runtime/py32/python.exe",
      "args": ["-u", "C:/Users/<you>/WorkBuddy AI/ni/multisim-ctrl/tools/mcp_server.py"]
    }
  }
}
```

手工验收（不需要 Agent）：

```bash
python tools/mcp_client.py
```

纯逻辑测试（不需要 Multisim，任意位数 Python）：

```bash
python tools/test_mcp_session.py      # 96 项（会话层）
python tools/test_layout.py           # 51 项（拓扑 + 坐标）
```

---

## 10. 第一版边界（明确不做）

| 不做 | 原因 |
| --- | --- |
| 真正的并联支路 / 并联到地 / 反馈 | 布局没验证过；`analyze()` 会明确报错而不是硬排 |
| 主干 > 4 级、多电源 | 同上 |
| 电感 / 二极管 / 运放 / 555 | 不在白名单 |
| 探针 > 9 | `LocalName` 序号超一位的命名规则未确认 |
| 电流探针 | 电压探针 + `I=V_R/R` 是已验证路径 |
| 交流扫频 / 蒙特卡洛 / 温度扫描 | COM 侧取数路径未验证 |
| LLM / 自然语言入口 | 先把执行 API 稳定下来。NL 那条线走 `nl2ir`，和 MCP 是并行的两个入口 |
| `RESISTOR_RATED` | 未验证 |
| `simulate` 的**硬**超时 | 需要把 COM 调用挪到可 kill 的线程，属重构；v0.6.2 只做软超时 + `timing` |
| MCP `progress` 通知 | 协议侧要发 `notifications/progress`，客户端要能处理通知；**接口位置已留好**（`simulate` 的 `timeout` / `timing`），等实测到 60 s、120 s、300 s 的真实分布再决定要不要做 |

### 关于 `simulate` 耗时（v0.6.2 的判断）

实测单次 **30 s 左右**（`timing.run_s` 占 98%，编译不到 0.5 s）。
很多 MCP 客户端默认超时是 60 s，所以这个数值得警惕 —— 但**不值得现在就重构**：

1. 现在电路只有 1~2 个无源元件，30 s 基本是 Multisim 启停的固定开销，不是规模问题
2. 先把 `timing` 暴露出去，让 Agent 和人都能看见时间花在哪
3. 等 P2（并联）、P3（运放/555）做完，再测 30 s / 60 s / 120 s / 300 s 的分布，
   那时才知道该做硬超时、还是该做异步 + 轮询

---

## 11. 两条入口的关系

```
                    自由中文
                       │
                       ▼
                    nl2ir          （确定性规则解析，59 项测试）
                       │
                       ▼
  Agent ──MCP──►  Circuit IR  ◄── circuit_session
   │                │
   └── 八个工具 ─────┘
                    ▼
                 msbuild
                    ▼
                  .ms14
                    ▼
                 Multisim
                    ▼
                  COM
                    ▼
                  结果
```

`nl2ir` 和 MCP 都产出 **同一份 Circuit IR**，走同一条执行链。
所以"中文入口"和"Agent 入口"不会给出两套不同的答案 ——
RC 低通在两条路上都是 0.70632 / −45.06°，这不是巧合，是同一份 IR。
