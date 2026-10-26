# MCP Tool API —— 电路执行器

> 版本：v0.6.0
> 定位：把已经验证过的 **Circuit IR + Multisim 执行链**包成一个 Agent 能直接用的接口。
> 代码：`tools/circuit_session.py`（业务逻辑）+ `tools/mcp_server.py`（协议层）。

---

## 1. 它不是"把 Python 函数套一层 MCP"

这是这一版最重要的设计决定。`nl_run.py` 那种"一句话跑到底"的脚本，
外面套个 MCP 壳也能用，但 Agent 只能整条调，没法一步步改电路、看中间状态。

所以这一版分了严格的两层：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 协议层 | `mcp_server.py` | JSON-RPC over stdio、tools/list、tools/call。**只做收发** |
| 会话层 | `circuit_session.py` | 电路句柄、语义参数映射、唯一性检查、自动命名、**自动布局**、分析类型匹配、结构化错误 |

会话层有真业务逻辑，所以它能单独测试（`test_mcp_session.py`，57 项，不需要 Multisim）。
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

## 3. 七个工具

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
| `AC_VOLTAGE` | `value=1.0, frequency=1000` | `value=1.0, params={5: 1000.0}` |
| `DC_POWER` | `value=5.0` | `value=5.0, params={}` |
| `RESISTOR_VIRTUAL` | `value=1000` | `value=1000.0` |
| `CAPACITOR_VIRTUAL` | `value=159e-9` | `value=1.59e-07` |
| `GROUND` | （不给） | `value=None` |

`params={5: 1000}` 里的 `5` 是 Multisim 的参数序号，Agent 永远看不到它 ——
返回里会翻回 `"parameters": {"frequency": 1000.0}`。

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

### `simulate`

```json
{"circuit_id": "c-...", "analysis": "transient"}
{"circuit_id": "c-...", "analysis": "dc"}
```

内部依次做：算布局 → 写回 IR → `validate()` → 编译 `.ms14` → 开 Multisim → 读探针 → 落盘。

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

返回里带 `sim_id`、`outputs`、`summary`（每通道 n/min/max/mean）、`record`、`waveform`。

> ⚠️ **`EnumOutputs` 只在 open 后调一次**这条铁律封在 `ir_sim` 里，Agent 碰不到。
> 见 [dc-static.md](dc-static.md)。

### `measure`

```json
{"sim_id": "s-...", "what": "all"}
{"sim_id": "s-...", "what": "amplitude", "probe": "P2"}
```

| `what` | 返回 |
| --- | --- |
| `all`（默认） | 全部 |
| `voltage` | 每通道 `mean / rms / min / max` |
| `amplitude` | 每通道正弦拟合幅值（仅 transient） |
| `phase` | 每通道相位（仅 transient） |
| `dc_voltage` | 每通道直流电压（仅 dc） |

`transient` 额外给 `gain`、`phase_deg`、`theory`；`dc` 给 `v_resistor`、`current`。

**拟合算法没有重写**，直接调 `ir_sim.fit_channels()`（最小二乘）。
`dc` 的电流仍是 `I = V_R / R`，`R` 来自 Multisim 的 `RLCValue`，
返回里用 `r_source` 字段标明来源，不假装用了电流探针。

`measure` 按**拓扑**找源网和地网，不依赖网络叫什么名字 —— 所以 Agent 把
网络命名成 `vcc` / `gnd` 也能正确算出电阻电压。

### `get_waveform`

```json
{"sim_id": "s-...", "probe": "V(探针1)", "max_points": 200}
```

不会把整条波形塞进返回值。默认给摘要（`n` / `min` / `max` / `mean` / `t_range`）
+ 最多 `max_points` 个采样点的预览（均匀抽样），完整数据在 `artifact` 指向的 CSV。

---

## 4. 数据模型：MCP 层不暴露什么

`tools_schema.json` 里做过一条自动检查：**不出现** `CiID` / `CiPort` /
`CIITSymbolComp` / `SimState`。

Agent 能看到的只有：

```
circuit_id
component   { refdes, family, part, value, parameters, pins, aliases }
connection  { name, pins[] }
probe       { name, net, kind, index }
simulation  { analysis, start, stop, sample_rate }
```

没有 donor 文件、没有坐标、没有 XML ID、没有参数序号。

---

## 5. 自动布局：坐标归底层管

`plan_layout()` 在 `simulate` 时按拓扑算坐标。第一版只支持**单电源串联链到地**，
用的是 v0.3.0 / v0.5.0 在真机上验证过的那套：

| 位置 | 坐标 |
| --- | --- |
| 电源 | `(300, 300)` |
| 第 1 个无源元件 | `(500, 300)` |
| 第 2 个无源元件 | `(700, 400)` |
| 地 | `(300, 420)` |

拓扑不是串联链时**明确报错**，而不是硬排一个没验证过的布局：

```json
{"code": "LAYOUT_UNSUPPORTED",
 "message": "网络 'in' 有 2 个分支（R1.1, R2.1）",
 "hint": "第一版只支持串联链；并联 / 多支路的布局还没验证过。",
 "context": {"net": "in", "branches": ["R1.1", "R2.1"]}}
```

无源元件超过 2 个也报错（布局只实测过 1~2 个）。

---

## 6. 错误设计

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
| `LAYOUT_UNSUPPORTED` | 拓扑不是串联链 | 说明第一版只支持什么 |
| `VALIDATION_FAILED` | IR 校验不过 | 带 `issues` 列表，逐条修 |
| `COMPILE_FAILED` | IR → `.ms14` 失败 | 通常是布局/引脚映射 |
| `SIMULATION_FAILED` | Multisim 没返回数据 | 检查探针是否落在导线上 |

---

## 7. 验收（实测，真跑 Multisim）

`tools/mcp_client.py` 起 server 子进程，**走真实 MCP 协议**（不是直接调 Python 函数），
建两个电路：

### RC 低通（1 V / 1 kHz / 1 kΩ / 159 nF）

| 检查项 | 结果 |
| --- | --- |
| `create_circuit` | `c-a580bc84c8` |
| 三个 `connect` 的自动命名 | `in` / `n1` / `0` |
| 探针用引脚名指定 | `R1.2` → 自动解析到 `n1` |
| `simulate` 自动选分析类型 | `transient`，30.1 s |
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
| `R` | 1000.0（来源：Multisim `RLCValue`） |
| **电流** | **0.005000 A** |

### 错误路径

| 场景 | 错误码 |
| --- | --- |
| `AC_VOLTAGE` + `analysis="dc"` | `ANALYSIS_NOT_SUPPORTED`（带 `supported: ["transient"]`） |
| 并联拓扑 | `LAYOUT_UNSUPPORTED`（指出 `branches: ["R1.1","R2.1"]`） |
| `add_probe(target="R1")` | `AMBIGUOUS_TARGET`（提示写成 `R1.1`） |
| 电感 | `UNKNOWN_COMPONENT_TYPE`（列出 5 种可用） |
| `AC_VOLTAGE` 缺 `frequency` | `MISSING_PARAMETER`（`context.field="frequency"`） |
| 跨网络硬连 | `PIN_ALREADY_CONNECTED` |

**48 项断言全部通过**，结果落在 `out/mcp/acceptance.json`。

---

## 8. 怎么接 Agent

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
python tools/test_mcp_session.py      # 57 项
```

---

## 9. 第一版边界（明确不做）

| 不做 | 原因 |
| --- | --- |
| 并联 / 多支路 | 布局没验证过；`plan_layout` 会明确报错而不是硬排 |
| 串联链 > 2 个无源元件 | 同上 |
| 电感 / 二极管 / 运放 / 555 | 不在白名单 |
| 探针 > 9 | `LocalName` 序号超一位的命名规则未确认 |
| 电流探针 | 电压探针 + `I=V_R/R` 是已验证路径 |
| 交流扫频 / 蒙特卡洛 / 温度扫描 | COM 侧取数路径未验证 |
| LLM / 自然语言入口 | 先把执行 API 稳定下来。NL 那条线走 `nl2ir`，和 MCP 是并行的两个入口 |
| `RESISTOR_RATED` | 未验证 |

---

## 10. 两条入口的关系

```
                    自由中文
                       │
                       ▼
                    nl2ir          （确定性规则解析，59 项测试）
                       │
                       ▼
  Agent ──MCP──►  Circuit IR  ◄── circuit_session
   │                │
   └── 七个工具 ─────┘
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
