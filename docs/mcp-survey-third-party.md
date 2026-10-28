# 第三方 Multisim MCP 解析与对比

> 对象：`Last-emo-boy/Multisim-MCP`（ISC）、`yxy050208/multisim-mcp`（MIT）
> 基线：本仓库 `multisim-ctrl` HEAD `4cc0fc8`（v0.9.0 + v0.9.1 截图 WIP）
> 日期：2026-10-27

## 0. 结论速览

三句话：

1. **两家都不是"AI 在 Multisim 界面里画电路"**，都是"程序生成图纸文件 → 交给 Multisim 打开 → 用 COM 跑仿真"。区别只在图纸从哪来：A 家从 SPICE 网表自己画 PNG，B 家从网表生成 XML 再编码成 `.ms14`。
2. **两家都没有真实 GUI 截图能力**。A 家的图是 Pillow 自绘或 COM 导出；B 家是 COM `GetCircuitImage` 导出 + SVG/CSV。我们新写的 `tools/screenshot.py`（`PrintWindow` + `PW_RENDERFULLCONTENT`）在这个维度上是**独有的**，虽然还没收尾。
3. **B 家的工程化程度远高于我们**（123 工具、32 位 COM worker 隔离、持久任务队列、SHA-256 证据链、三态验收），**A 家的元件覆盖面远高于我们**（61 工具、完整 COM API 面）。但两家的"原理图真实度"都不如我们的 donor 克隆——他们图纸上的扩展器件是**通用载体符号**。

一句话选型：**B 家是要抄的架构，A 家是要抄的 API 面，我们自己的 donor 克隆路线不能丢。**

## 1. 方法说明

| 结论类型 | 来源 |
|---|---|
| 工具数量、工具名 | 直读 `server.py` / `tool_profiles.py` 源码 |
| 图像是截图还是渲染 | 直读 `schematic_render.py`、`multisim_client.py`，确认无 `PrintWindow`/`BitBlt`/`pyautogui` |
| `.ms14` 读写方式 | 直读 `native_xml.py`、`multisim_client.py` 的 `Ms14Codec` |
| COM 隔离架构 | 直读 `com_worker.py` 全文 |
| 能力边界 | 两边 README 自述 + 源码注释（注释里写限制的，可信度高） |

未做：**没有克隆运行**。以下"能做到什么程度"是基于代码路径的判断，不是实测。凡我拿不准的地方都标了「未实测」。

## 2. A 家：`Last-emo-boy/Multisim-MCP`

### 2.1 它是什么

一个**薄 COM 封装 + 大量程序化出图/出报告**的单文件 MCP server。

- `src/multisim_mcp/server.py` **75.7 KB**，61 个 `@mcp.tool()` + 7 个 `@mcp.prompt()` 全在这一个文件里注册。
- `com_adapter.py` 28.8 KB，只做一件事：把 `win32com.client.Dispatch("MultisimInterface.MultisimApp")` 包成 Python 方法。
- 其余 12 个 `tools/*.py` 是纯 Python 加工层（模板、渲染、报告、扫描、DRC）。

### 2.2 工具集（61 个，按类）

| 类 | 数量 | 代表 |
|---|---|---|
| 会话/文件 | 10 | `connect` `open_design` `open_netlist` `save_design_as` `export_circuit_image` `create_snippet` |
| 枚举/报告 | 8 | `list_components` `list_inputs` `list_outputs` `export_netlist` `export_bom` |
| 修改 | 7 | `set_rlc_value` `replace_component` `set_input_data_raw` `set_circuit_parameter_value` |
| 仿真 | 12 | `run_transient` `run_ac_sweep` `run_dc_operating_point` `run_command_line` `parameter_sweep` |
| 输出采集 | 5 | `set_output_request` `get_output_data` `summarize_output` |
| 虚拟仪器 | 3 | `function_generator` `oscilloscope` `plot_waveform` |
| 模板/构建 | 5 | `list_circuit_templates` `materialize_design_template` `build_netlist` |
| 元件目录 | 2 | `search_component_catalog` `list_component_categories` |
| DRC / 扫描 / 测量 | 4 | `check_design_rules` `transient_sweep` `measure_signals` |
| 报告 | 3 | `simulation_report` `generate_markdown_report` |
| 渲染 | 1 | `render_netlist_schematic` |

7 个 prompt 是工作流向导：`analyze_circuit`、`spice_analysis`、`parameter_sweep`、`troubleshoot_circuit`、`export_report`、`lab_report`、`instrument_workflow`。

### 2.3 能做到什么程度

能做到：

- 打开**用户自己已有的** `.ms14`，枚举元件、改 RLC 值、跑 DC/AC/TRAN、取回波形数据、导出网表/BOM。
- 打开 `.cir` 网表，交给 Multisim 命令行引擎跑 SPICE（`run_spice` 走 nutmeg）。
- 参数扫描、多变体瞬态、结构化测量（从波形算指标）。
- 生成 Markdown / 自包含 HTML 报告。

**做不到 / 有硬缺陷**：

- **不能从零造一个 `.ms14`**。它的"生成"只有两条路：① `materialize_design_template` 产出 `.cir`（+ 可选原理图 PNG）；② `build_netlist` 产出网表文本。**全程没有一处写 `.ms14` 二进制**——没有 magic、没有 DCL、没有 XML 序列化。
- **`open_netlist` + `export_circuit_image` 出来是空白网格**。这是它自己在 `schematic_render.py` 注释里承认的：`"Multisim's COM API cannot render programmatically loaded netlists (open_netlist + export_circuit_image produces blank images)"`。它的解法是**用 Pillow 自己画一张 PNG 顶上**。
- 所以它的"原理图"对 Agent 生成的电路而言，**是 Pillow 画的示意图，不是 Multisim 的图**。
- 无 32 位检查（`connect()` 里没有位数判断），无残留进程清理，无重试，无超时。`OpenFile` 传不存在路径会让 COM server 直接崩（这条 B 家踩过，A 家没有防护）。
- `tests/test_core_tools.py` 仅 3 KB，只测纯 Python 工具，**COM 路径零自动化测试**。

### 2.4 优势 / 劣势

优势：

- **COM API 面铺得最全**：61 个工具基本把 `MultisimInterface` 的类型库翻了一遍，包括分段元件（U1A/U1B）、设计变体、电路参数、虚拟仪器状态。这个"API 面清单"本身就是资产。
- 依赖轻（Pillow + matplotlib + pywin32），单文件好读。
- 工具描述写得细，把 XSPICE 的坑（不支持 `wrdata`、节点电压要用 `$out` 不能 `v(out)`）直接写进 tool description——**这是给 Agent 看的，很聪明**。
- 统一返回结构 `{ok, data, error_code, error_message, suggested_recovery}`，`suggested_recovery` 对 Agent 自纠错有用。

劣势：

- 不生成 `.ms14` → 产出的东西**在 Multisim 里不可继续编辑**，只能当实验脚本用。
- 自绘图冒充原理图（见 2.3），交付物经不起"这是 Multisim 画的吗"一问。
- 无隔离、无恢复、无测试。

## 3. B 家：`yxy050208/multisim-mcp`

### 3.1 它是什么

一个**工程化程度很高的"实验流水线"**，不是简单的工具集合。

- 123 个工具（`full` profile，README 自述），通过 `tool_profiles.py` 分成 `core` / `experiment` / `optimization` / `full` 四档暴露。`MULTISIM_MCP_TOOL_PROFILE` 环境变量控制。
- `mcp_server/multisim_mcp/` 下约 **150 个模块**，`docs/` 约 90 篇，`tests/` 约 60 个。

### 3.2 三个关键架构（这是最该抄的部分）

**① 32 位 COM worker 子进程**

`com_worker.py` 是一个独立的 32 位进程，协议是**私有换行分隔 JSON**：

```
{"protocol_version":N, "id":"...", "target":"client|codec|system|control",
 "method":"...", "args":[...], "kwargs":{...}}
```

- **方法白名单**：`_CLIENT_METHODS`（33 个）与 `_CODEC_METHODS`（2 个）是 `frozenset`，白名单外的 `method` 直接 `PermissionError`。
- **单线程持有 COM apartment**，一个读线程收请求、主线程串行执行。
- **心跳**：执行期间回调 `emit_heartbeat()`，父进程据此判活。
- **取消**：`control/cancel` 请求单独走旁路，设置 `threading.Event`，长任务（`run_command_file`）通过 `cancel_requested` 回调感知。
- **父进程死亡自杀**：`_watch_parent` 每 0.5 s 检查，父进程没了就 `os._exit(70)`，不留孤儿 COM。
- **请求大小上限** `MAX_REQUEST_BYTES`，超了直接拒。

**② 外部 Node 工具做 `.ms14` 编解码**

`Ms14Codec` 只是 `electronics-workbench-decoder@0.2.0` 这个 npm 包的命令行壳：

```python
subprocess.run([*self._base_cmd("ewd"), source])            # decode: .ms14 -> .xml
subprocess.run([*self._base_cmd("ewe"), "--format","multisim",
                "--output", out, source_xml])               # encode: .xml -> .ms14
```

Python 侧**没有** magic、没有 DCL、没有分块——全在 Node 包里。它只额外做了安全隔离：拒绝 `.cmd`/`.bat` shim，必须真 `node.exe`；Windows 上禁用 npx 回退。

**③ 本地模板包 bootstrap**

因为不能分发 NI 资产，公开仓库不带 XML 模板。用户必须跑：

```powershell
python tools/bootstrap_local_component_pack.py --output C:\MultisimMcp\component-pack
```

它连上本机已授权的 Multisim，**新建一个空白电路**，把工程骨架抓下来当模板。然后 `MULTISIM_MCP_TEMPLATE_DIR` 指过去。

> 这条对我们有直接启发：我们的 donor 池（`registry/components.json` 192 条）本质上也是"从本机样本里提取的元件模板"，思路一致，但我们没做"空白工程骨架"这一层。

### 3.3 能做到什么程度

能做到（README 自述 + 源码结构支持）：

- 从受限 SPICE 网表 → **生成可编辑 `.ms14`** → 真实 Multisim 打开 → **反向枚举验证** → 导出 PNG → 跑 OP/AC/TRAN → 导出 raw/CSV/SVG → 出中英双语 HTML/PDF 报告 + `manifest.json`（SHA-256）。
- 持久任务队列：`submit_circuit_experiment` 立即返回 `job_id`，支持查询/取消/重试；worker 崩了不拖垮 MCP server，未完成任务重启后重新排队。
- 参数/容差/温度/Monte-Carlo 扫描（每次最多 100 个运行点）。
- 版本化 `ExperimentSpec` + 三态判定：`pass` / `fail` / `unverified`，**证据缺失时只给 `unverified`，不猜**。
- 自然语言前端：`plan_natural_rectifier` → `run_natural_rectifier` → `optimize_natural_rectifier`，覆盖 RLC / 运放 / 共射 / 整流 / 双板数字。
- 设计补丁事务：`evaluate_design_patch` → `approve_design_patch` → `apply_design_patch` → `revert_design_patch` / `recover_design_patch`。

做不到 / 有硬边界（它自己写明的）：

- **原理图上的扩展器件是"通用载体符号"**：README 原文「扩展族暂用通用载体符号」。也就是说 B 家图纸上的运放/晶体管，**长得不一定是 Multisim 库里那个真实型号的符号**。这是"网表优先"路线的必然代价。
- **依赖外部 Node 包**做编解码——一个 npm 包决定你能不能写 `.ms14`。
- **必须 bootstrap 本地模板包**，否则跑不起来。对新用户是硬门槛。
- 自动生成的探针**不作为实验数据来源**（README 明说），数据来自同一网表经命令引擎执行的结果。
- 覆盖面靠"实测过的有限案例"堆出来：整流、共射、运放、双板数字，每个都配一篇 acceptance 文档。**不是通用能力**。

### 3.4 优势 / 劣势

优势：

- 架构分层的完整度：**worker 隔离 → job 队列 → 流水线 → 证据链 → 报告**，每一层都有失败恢复。
- **验收是可计算的**：`ExperimentSpec` 里写 `operator: at_least|at_most|between|approximately` + `target` + `tolerance_percent`，跑完自动出 PASS/FAIL。这是"不许降低标准"的工程化实现。
- **证据链**：`workspace_manifest` SHA-256 + `manifest.json`，产物可移交、可复核。
- 工具分层（profile）解决"上下文有限的客户端装不下 123 个工具"。
- 文档纪律：每个能力一篇 acceptance 文档，写清"覆盖了什么、没覆盖什么、什么版本实测的"。

劣势：

- **重**。150 模块 / 90 篇文档 / 60 个测试，新贡献者上手成本高；调试一次要穿过 worker 协议。
- **依赖链长**：pywin32 + 32 位 Python + Node + npm 包 + 本地模板包。任何一环断，整条链不通。
- **原理图真实度打折**（通用载体符号）。
- 大量工具是"一次性验收案例"包装成的（`run_natural_rectifier` 这种），**通用性存疑**——换个拓扑就要新写一个 `natural_*.py`。

## 4. 三方横向对比

| 维度 | 我们 `multisim-ctrl` | A：Last-emo-boy | B：yxy050208 |
|---|---|---|---|
| MCP 工具数 | **8** | 61（+7 prompt） | 123（4 档 profile） |
| 可用元件数 | **6**（registry 索引 192，仅 1 个 enabled） | 全 COM API 可达（受 Multisim 库限制） | 网表级（SPICE 器件 + 通用载体） |
| 写 `.ms14` | **自研 codec**（magic + DCL 分块 + XML） | ❌ 不写 | ✅ 但靠外部 npm 包 |
| 图纸来源 | **donor 克隆真实库元件** | Pillow 自绘 / COM 导出 | 网表 → XML 模板 → encode |
| 图纸真实度 | 高（是真正的 1N4007G 符号） | 低（自绘示意图） | 中（扩展族用通用载体符号） |
| 真实 GUI 截图 | **有**（`screenshot.py`，PrintWindow，未收尾） | ❌ | ❌ |
| COM 隔离 | ❌ 整个 server 跑 32 位 | ❌ 同进程 | ✅ 32 位 worker 子进程 + 心跳 + 取消 + 父死自杀 |
| 任务队列/恢复 | ❌ | ❌ | ✅ 持久 job + 崩溃重排队 |
| 参数扫描 | ❌ | ✅ `parameter_sweep` `transient_sweep` | ✅ 含 Monte-Carlo / 温度 / 容差 |
| 验收判定 | 手工脚本 `validate_acceptance.py` | ❌ | ✅ 版本化 spec + 三态 |
| 证据链 | `acceptance.json`（无哈希） | ❌ | ✅ SHA-256 manifest |
| 报告生成 | ❌ | ✅ MD + HTML | ✅ MD/JSON/HTML/PDF + manifest |
| 第三方依赖 | **零**（纯标准库） | Pillow + matplotlib + pywin32 | pywin32 + Node + npm 包 + 模板包 |
| 测试 | 每个能力有独立回归脚本 | 3 KB（只测纯 Python） | ~60 个测试文件 |
| 代码量 | ~200 个 `tools/*.py`（大量 p1..p19 探路脚本） | 单文件 75 KB + 12 模块 | 150 模块 |

## 5. 三条最关键的认知

### 5.1 图像：我们在这条线上是唯一的，但还没兑现

用户 v0.9.1 的硬要求是"必须是真实 Multisim GUI 窗口截图"。查完两家：

- A 家：Pillow 自绘 + COM 导出，**没有一处屏幕抓取代码**。
- B 家：COM `GetCircuitImage` 导出 + SVG，**同样没有**。

我们 `tools/screenshot.py` 用的 `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)` + `GetDIBits`，是三家唯一的真实窗口抓取。**这条护城河值得收尾**——但要如实说清楚它现在的状态（`zoom_to_fit` 未验证、TSTOP 写入未验证、符号不渲染）。

同时要警惕：A 家的 `render_netlist_schematic` 正是"用渲染冒充截图"的反面教材，它自己的 README 都写了 `open_netlist + export_circuit_image` 出来是空白网格。**如果我们走自绘兜底，必须显式标注"这不是截图"**，否则就是用户明令禁止的那件事。

### 5.2 元件：两条路线各有死穴，我们在中间

- 我们：**donor 克隆真实元件** → 图纸真实、可编辑、符号对。死穴是覆盖面（6 个），每个新元件要人工验证引脚/参数槽。
- B 家：**网表优先 + 通用载体** → 覆盖面大，但符号不真。死穴是"看着像电路，点开不是那个器件"。
- A 家：**不造 `.ms14`** → 根本没这个问题，也没这个能力。

对我们的启示：**别为了扩元件去学 B 家的"通用载体"**。那会把我们唯一的优势（真实元件）换成他们的劣势。扩元件应该走"registry 索引 192 → 逐个 enable + 验收"的路，慢但对。

### 5.3 32 位：这是我们最该马上改的架构债

我们整个 MCP server 跑在 `runtime/py32/python.exe`（因为 CLSID 只注册在 WOW6432Node）。后果：

- Agent 侧任何 64 位依赖都用不了；
- COM 一崩（比如 `OpenFile` 传坏路径），**整个 MCP server 跟着死**，session 全丢；
- 没有心跳，Agent 无法区分"仿真在跑"和"进程卡死"。

B 家的 worker 方案不复杂（`com_worker.py` 全文不到 300 行，协议就是换行 JSON + 白名单），但收益很大。**这是投入产出比最高的一条**。

## 6. 可借鉴清单（按性价比排序）

| 优先级 | 借鉴项 | 出处 | 怎么用在我们身上 | 与 v0.9.1 冲突吗 |
|---|---|---|---|---|
| **P0** | 三态验收 `pass/fail/unverified` | B `design_verification.py` | `acceptance.json` 的 12 项判定加 `unverified` 态；**证据缺失就写 unverified，不写 fail 也不写 pass** | 不冲突，正是用户要的"不许降低标准" |
| **P0** | 验收算子 `at_least/at_most/between/approximately` + `tolerance_percent` | B `requirement_contract.py` | Case A 的 `fc≈500Hz`、`gain≈0.707`；Case C 的 `Vout≈0.5Vin` 直接用 `approximately` + 容差表达 | 不冲突，直接可用 |
| **P1** | 工具白名单 + 单线程 COM apartment | B `com_worker.py` | 拆 `py32_worker.py`：换行 JSON 协议、`_METHODS` frozenset 白名单、父死自杀 | 不冲突，但是新工程 |
| **P1** | 心跳 / 取消旁路 | B `com_worker.py` | `simulate()` 长任务期间吐 heartbeat，Agent 可判活；取消走独立通道 | 不冲突 |
| **P1** | `native_capability_probe` | B `multisim_client.py` | 启动时探测 `addcomponent/connect/wire` 到底支持不支持，**别假设**。我们摸黑点菜单吃的亏就是这个 | 不冲突 |
| **P1** | SHA-256 manifest | B `workspace_manifest.py` | `acceptance.json` 旁加 `manifest.json`，对 `circuit.ms14`/`waveform.csv`/两张 PNG 出哈希 | 不冲突，20 行代码 |
| **P2** | 工具 profile 分层 | B `tool_profiles.py` | 8 个工具用不上。但 `capture_screenshot` 上线后应该**默认关闭、显式开启**（它要抢前台、会杀 Multisim 进程） | 不冲突 |
| **P2** | 空白工程骨架模板 | B `bootstrap_local_component_pack.py` | 可能能解决"符号不渲染"：不从 sample 克隆，而是从**空白新工程**取骨架再挂元件 | **可能冲突**，需先验证 |
| **P2** | 统一错误返回 `{ok,error_code,suggested_recovery}` | A `server.py` | 我们已有 `CaptureError(code, message, hint)`，可推广到 8 个工具 | 不冲突 |
| **P3** | 持久 job 队列 | B `job_engine.py` | 单机单 Agent 场景收益低，缓做 | 不冲突 |
| **P3** | 把 API 坑写进 tool description | A `server.py` | 已有（`_registry_part_doc()` 自动生成），可补 XSPICE 类坑 | 不冲突 |

## 7. 明确不该学的

1. **不要用自绘 PNG 冒充原理图**（A 家 `render_netlist_schematic`）。用户 v0.9.1 规格明确禁止，而且这是"看起来交付了、实际交付不了"的典型。
2. **不要为了扩元件改用通用载体符号**（B 家）。会丢掉我们唯一的真实感优势。
3. **不要现在就去堆工具数量**。61 个 / 123 个工具对"AI 能不能自己设计电路"这件事没有帮助——两家都有一堆工具，但都还在写 `natural_rectifier.py` 这种一次性案例。**工具多 ≠ 会设计**。
4. **不要引入 npm 依赖做编解码**。我们自研 DCL codec 是纯标准库零依赖，这是优势不是负担。

## 8. 对 v0.9.1 的直接影响

按用户原定的三个 case，借鉴后应该这样落：

- **`acceptance.json` 改三态**：12 项判定每项写 `pass` / `fail` / `unverified` + `evidence` 路径。截图项在 `screenshot.py` 未收尾前**必须写 `unverified`，不能写 `pass`**。
- **验收算子版本化**：照 B 家的 `{"metric":"cutoff_frequency","operator":"approximately","target":500,"tolerance_percent":10}` 写，别写自然语言。
- **加 `manifest.json`**：对每个 case 的 5 个产物出 SHA-256。
- **报告里如实写**：两家都没有真实 GUI 截图；我们的截图能力是新的、且 `zoom_to_fit`/TSTOP 未验证；`.ms14` 符号不渲染是已知缺陷。

## 9. 未验证事项（别当结论用）

- 两家的真实运行表现：**没跑过**。上面"能做到什么程度"全部来自读码 + 自述。
- B 家 123 个工具里有多少是真跑通的、多少是包装的一次性案例：只看了 `tool_profiles.py` 的名字清单，没逐个查实现。
- A 家的 61 个工具在 Multisim 14.3.3 上是否都能用：它的 `com_adapter.py` 没有版本探测，类型库不匹配时会静默失败还是报错，没测。
