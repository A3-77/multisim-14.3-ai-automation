# 两个第三方 Multisim MCP：骨架拆解 + 实测复现

> 不是读 README 猜的。两个仓库都克隆到本机、装依赖、连真的 Multisim 14.3.3 跑过。  
> 所有"能做到/做不到"后面都有文件或报错兜底。  
> 实测日期：2026-10-27　环境：Windows / Multisim 14.3.3 / 32 位 Python 3.11.9 / pywin32 312 / Node 22.22.2

---

## 0. 一句话结论

|              | A 家 `Last-emo-boy/Multisim-MCP`         | B 家 `yxy050208/multisim-mcp`            |
| ------------ | --------------------------------------- | --------------------------------------- |
| 真正跑通的        | **SPICE 命令行仿真**（分压器 DC 扫描 0→10V 得 0→5V） | **网表 → 可编辑 `.ms14` → 真 Multisim 仿真出波形** |
| 实测崩掉的        | 改 RLC 值、启动交互式仿真、图像格式常量                  | 无（本次没跑到崩）                               |
| 能不能造 `.ms14` | **不能**                                  | **能，66 KB，符号完整**                        |
| 学到的最重要一件事    | 图像格式枚举真实值是 PNG=0 / JPG=1 / BMP=2        | 骨架用 COM 新建空白工程取，元件从官方 sample 里挑"能存活的"   |

**最有价值的单条发现**：B 家从一句 SPICE 网表生成的 `.ms14`，在真 Multisim 里**符号全部正常渲染**；我们自己的 `.ms14` 同一路径导出**符号全丢**。这坐实了符号不渲染是我们 donor 克隆的问题，不是 Multisim、不是版本、也不是查看器。

---

## 1. A 家骨架拆解

```
src/multisim_mcp/
├── server.py            75.7 KB  ← 61 个 @mcp.tool() + 7 个 @mcp.prompt() 全在这一个文件
├── com_adapter.py       28.8 KB  ← 唯一的 COM 封装，41 个方法，纯薄壳
├── session.py            6.9 KB  ← 会话状态 + 审计日志(~/.multisim_mcp/audit_log.json)
├── models.py             6.6 KB  ← Pydantic 模型
└── tools/               ← 12 个纯 Python 加工层，不碰 COM
    ├── circuit_templates.py  46.0 KB  ← 内置 SPICE 模板库
    ├── schematic_render.py   36.2 KB  ← 用 Pillow 自己画原理图
    ├── instrument_tools.py   30.5 KB  ← 函数发生器 / 示波器 / plot_waveform
    ├── component_catalog.py  23.2 KB
    ├── signal_measure.py     22.7 KB
    ├── netlist_builder.py    21.5 KB
    ├── design_checks.py      20.3 KB
    ├── transient_sweep.py    17.8 KB
    ├── spice_tools.py        15.1 KB  ← run_spice：8.3 短路径 + ASCII 网表，最扎实的一块
    ├── markdown_report.py    13.4 KB
    └── simulation_tools.py / report_tools.py / file_tools.py / modify_tools.py / enum_tools.py / output_tools.py
tests/test_core_tools.py   3 KB  ← 只测纯 Python，COM 路径零自动化测试
sim/  inv_amp.cir, dc_sweep.cmd（里面写死了作者的 E:/Playground 路径）
```

**架构一句话**：`MCP 协议层 → 61 个 tool 函数 → 一个 28 KB 的 COM 薄壳 → Multisim`。所有"智能"在 tools/ 那层用 Python 算，COM 层只做转发。

### 实测结果（打开 NI 官方 `LowPassFilter.ms14`）

| 步骤                              | 结果                                                         | 证据                                  |
| ------------------------------- | ---------------------------------------------------------- | ----------------------------------- |
| `connect`                       | ✅ 1157 ms，返回 `Multisim 14.3`                               | `out_a/report_a.json`               |
| `open_file`                     | ✅ 680 ms，CircuitName=`LowPassFilter_copy`                  | 同上                                  |
| `enum_components`               | ✅ `['C1','R1','R2','U1','V1','V2','V3']`                   | 同上                                  |
| `enum_inputs`                   | ✅ `['V1','V2','V3']`                                       | 同上                                  |
| `set_rlc_value`                 | ❌ `RLCValue set failed: 'int' object is not subscriptable` | 同上                                  |
| `run_simulation`                | ❌ `RunSimulation failed: (-2147352562, '无效的参数数目。')`        | `out_a/report_a_sim.json`           |
| `get_circuit_image`             | ⚠️ 成功但**格式错**：2764854 字节 BMP 存成 `.png`                     | `out_a/probe_fmt.json`              |
| `report_netlist` / `report_bom` | ✅ 生成，但**中文全乱码**（`_uc...`）                                  | `out_a/netlist.txt`                 |
| `do_command_line`（SPICE 路径）     | ✅ **真跑通**：分压器 Vin 0→10V，$out 0→5V                          | `artifacts/07_A家_SPICE_DC扫描_日志.txt` |

### 三个 bug 的具体成因（都定位到了源码行）

1. **改 RLC 值必崩**：`com_adapter.py:332` 写 `self._circuit._oleobj_.GetIDsOfNames("RLCValue")[0]`。pywin32 312 下这个方法**直接返回 int（28），不是元组**，`[0]` 就炸了。  
   我们自己 `msc.py:82` 的 `_prop_put` 做的是同一件事，只是没有 `[0]`，所以能用。**一行之差。**
2. **启动不了仿真**：`com_adapter.py:577` 调 `self._circuit.RunSimulation()` **不带参数**。14.3 要求 `RunSimulation(seconds, pause)`，报"无效的参数数目"。  
   对比 B 家 `multisim_client.py` 调的是 `RunSimulation(duration, False)` —— 带参数。
3. **图像格式常量整张反了**：A 家声明 `IMAGE_FORMAT_BMP=0, JPG=1, PNG=2`。  
   实测三次调用取文件头：
   - `0` → `89 50 4E 47` = **PNG**
   - `1` → `FF D8 FF E0` = **JPEG**
   - `2` → `42 4D` = **BMP**  
     真实映射是 **PNG=0 / JPG=1 / BMP=2**。A 家默认"导出 PNG"实际得到 2.7 MB 的 BMP，还硬存成 `.png`。
4. 附带：`report_netlist` / `report_bom` 的中文全是 `_uc...` 转义乱码。原因是没有做 BSTR 编码回正——我们 `msc.py:_fix()` 那段 `text.encode("latin-1").decode("utf-8")` 就是干这个的，A 家没有。

> 这些不是"环境特殊"。pywin32 312 是当前主流版本，Multisim 14.3 是主流版本。**它大概率没在端到端环境里跑过**——测试文件只有 3 KB，且只测纯 Python。

---

## 2. B 家骨架拆解

```
mcp_server/multisim_mcp/            147 个模块
├── server.py                194.8 KB  ← 123 个工具注册
├── cli.py                   148.8 KB  ← doctor / config / harness-skills / model
├── schematic_builder.py     209.3 KB  ← 最重的一块：SPICE 网表 → Multisim 原生 XML
├── com_worker.py            ~10 KB    ← 32 位 COM 子进程（协议 + 白名单 + 心跳 + 父死自杀）
├── com_worker_client.py / worker_protocol.py
├── job_engine.py             34.3 KB  ← 持久任务队列，崩溃恢复 + 重排队
├── multisim_client.py        38.6 KB  ← COM 客户端 + Ms14Codec（调外部 node 的 ewd/ewe）
├── component_placement.py    42.5 KB / layout_optimization / orthogonal_routing / layout_validation
├── design_verification.py    39.6 KB  ← 三态判定 pass/fail/unverified
├── design_patch_*.py (6 个)           ← 事务式补丁：evaluate → approve → apply → revert/recover
├── natural_rectifier.py / natural_rlc.py / natural_opamp.py / natural_common_emitter.py  ← 各带 _run.py
├── experiment_pipeline.py / experiment_sweep.py / formal_report.py
├── workspace_manifest.py              ← SHA-256 证据链
├── tool_profiles.py                   ← core / experiment / optimization / full 四档
└── templates/manifest.json            ← 只有清单，XML 不在仓库（授权原因）

tools/bootstrap_local_component_pack.py  196 行  ← 从本机 NI sample 抽元件模板
compatibility/components-14.3.json       ← 每个元件在 14.3 上的引脚映射，且必须"已验证"
docs/ 约 90 篇   tests/ 约 60 个
```

**架构一句话**：`MCP 前端(可 64 位) → 32 位 COM worker 子进程 → Multisim`，中间夹一条 `网表 → XML → .ms14` 的编译链，外面套任务队列和证据链。

### 关键设计一：模板包从"本机已授权安装"里抽，不随仓库分发

`bootstrap_local_component_pack.py` 干三件事：

1. 从 `C:\Users\Public\Documents\National Instruments\Circuit Design Suite 14.3\samples` 里，**为每种元件挑一个具体 refdes**：


   ```python
   Extraction("LabVIEW Multisim API Toolkit/RLC Values/RLC Values.ms14", "R1", "R")
   Extraction("LowPassFilter.ms14", "C9", "C")
   Extraction("Analog/ClassBPushPullAmp.ms14", "D1", "D")
   Extraction("LowPassFilter.ms14", "U4", "OPAMP5")
   ```
2. 用 `ewd` 把 sample 解成 XML，按 refdes 把那个元件的 element/port/model 抠出来，各存一个 `.xml`。
3. **骨架不取 sample，而是用 COM 新建一个空白工程再 SaveAs**：
   ```python
   blank_client.connect(); blank_client.new_circuit(); blank_client.save_circuit(blank_ms14)
   # 注释原文：Installed samples may retain a much older file format than the local
   #           application. Generate a blank design through the licensed Automation API
   #           so structural scaffolding always matches the installed Multisim.
   ```

第 3 点是关键。**它保证图纸骨架和本机版本完全一致**，元件只是往骨架里挂。

还有个细节值得记：他们的注释里写着

> `LowPassFilter.ms14/R11 looks structurally valid but Multisim 14.3 drops transplanted instances from its native netlist. The API Toolkit's R1 is verified to survive open/save/reverse-netlist generation.`

也就是说**他们也踩过"克隆的元件被 Multisim 静默丢掉"**，解法是"换 donor 直到找到能存活的"。这跟我们 v0.9 选 donor 的经验是同一件事。

### 关键设计二：32 位 COM worker

`com_worker.py` 全文不到 300 行，协议就是**换行分隔 JSON**：

```json
{"protocol_version":N,"id":"...","target":"client|codec|system|control","method":"...","args":[],"kwargs":{}}
```

- `_CLIENT_METHODS`（33 个）/ `_CODEC_METHODS`（2 个）是 `frozenset` 白名单，白名单外直接 `PermissionError`；
- 一个读线程收请求，**主线程独占 COM apartment 串行执行**；
- 执行期间回调 `emit_heartbeat()` 吐心跳；
- `control/cancel` 走旁路，设 `threading.Event`，长任务通过 `cancel_requested` 回调感知；
- `_watch_parent` 每 0.5 s 检查父进程，父死就 `os._exit(70)`，不留孤儿。

### 实测结果

| 步骤                                                | 结果                                                                                                    |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `npm install electronics-workbench-decoder@0.2.0` | ✅ 1 个包，产出 `ewd` / `ewe`                                                                               |
| `bootstrap_local_component_pack.py`               | ✅ **162 个模板文件**，连真 Multisim 建空白工程取骨架                                                                  |
| `build_schematic(RC 网表, probe_nets=["in","out"])` | ✅ `unsupported: []`，`layout_validation: pass`，2 个探针 `point_selected_on_wire: true`，XML **417,590 字节** |
| `Ms14Codec().encode()`                            | ✅ **`.ms14` 66,460 字节**                                                                               |
| `decode` 回读                                       | ✅ 417,590 字节，`R1` / `C1` / `Vin` 都在                                                                   |
| 真 Multisim GUI 打开                                 | ✅ **符号、数值、探针、导线全部正常**（见证据 02）                                                                         |
| 瞬态分析 → 图示仪                                        | ✅ 真实 GUI 截图，两条曲线（见证据 03）                                                                              |
| COM 取波形数值                                         | ✅ `V(in)` amp **1.0064**；`V(out)` amp **0.8582**，phase **−31.88°**                                    |

**物理核对**（R=1k，C=100n，f=1kHz）：

- fc = 1/(2π·1000·100n) = **1591.55 Hz**
- 理论增益 = 1/√(1+(1000/1591.55)²) = **0.8467** → 实测 0.8582（+1.4%）
- 理论相位 = −atan(1000/1591.55) = **−32.14°** → 实测 −31.88°（差 0.26°）

误差来自 204 采样点 + 起始暂态没完全跳过，属正常量级。**数值是对的。**

---

## 3. 证据图（都在 `ref/artifacts/`）

| #  | 文件                           | 说明                                                                                             |
| -- | ---------------------------- | ---------------------------------------------------------------------------------------------- |
| 01 | `01_A家_官方样本_API导出PNG.png`    | A 家 `GetCircuitImage(0)` 导出的 NI 官方 LowPassFilter。**符号完整、标题栏都在** —— 证明导出路径本身没问题                 |
| 02 | `02_B家_网表生成的ms14_真GUI截图.png` | **B 家从 SPICE 网表生成的 `.ms14`，在真 Multisim 窗口里的 PrintWindow 截图**。Vin 正弦源、R1 1kΩ、C1 100nF、地、两个探针，全对 |
| 03 | `03_B家_瞬态分析_图示仪真实截图.png`     | 同一份 `.ms14` 跑瞬态分析后的「图示仪视图」窗口截图。青线输入 1.0V，深蓝线输出 ~0.85V 滞后                                       |
| 04 | `04_B家_同一ms14_API导出PNG.png`  | B 家产物用 `GetCircuitImage(0)` 导出，和 02 互相印证                                                       |
| 05 | `05_我方ms14_同路径导出_符号丢失.png`   | **我们自己的 `rc_lowpass.ms14`，走完全相同的导出路径**：V1 / C1 / GND 符号全丢，R1 错位，导线是黑色不是红色                      |
| 06 | `06_B家_生成的source.ms14`       | B 家产出的 `.ms14` 原件，66,460 字节，可以直接用 Multisim 打开验证                                                |
| 07 | `07_A家_SPICE_DC扫描_日志.txt`    | A 家 `DoCommandLine` 的 nutmeg 输出，Vin 0→10 对应 $out 0→5                                           |

**02 / 03 是真实 GUI 窗口截图**（`PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)` + `GetDIBits`），不是 API 导出、不是重绘。01 / 04 / 05 是 API 导出（`GetCircuitImage`），用途是三方对照。

---

## 4. 05 这张图说明了什么（对我们最重要）

同一台机器、同一个 Multisim、同一个导出函数：

- 打开 NI 官方 sample → 完整（01）
- 打开 B 家生成的 → 完整（04）
- 打开我们生成的 → **符号丢失**（05）

所以：**不是 Multisim 的问题，不是版本问题，不是导出 API 的问题，是我们生成的 `.ms14` 本身有问题。**

差别在生成方式：

|      | 我们                                                    | B 家                                                                                  |
| ---- | ----------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 图纸骨架 | 从某个 sample `.ms14` 深拷贝后裁剪                             | **COM 新建空白工程再 SaveAs**（保证和本机版本一致）                                                    |
| 元件来源 | 从 donor `.ms14` 深拷贝 `CiComponent` + symbol 子对象        | 从官方 sample 里**逐个 refdes** 抠出来，且要求"open/save/反向网表能存活"                                 |
| 变换语义 | 手动重映射 `Transformer-M20/M21`，跳过 `CIITPinConnectorComp` | 用 `_symbol_pin_info()` 从 symbol 的 pin 几何反推中心，再归一化 `dx,dy = round((center_x-63)/9)*9` |
| 文本标签 | 跟着符号一起平移                                              | **符号几何和文字反向旋转分开处理**（`CIITSymTextCompName` / `CIITSymTextCompValue` 单独设矩阵）            |

我们的现象（符号不渲染但网表正确）指向：**symbol 的绘制子对象和 `CiComponent` 的变换矩阵语义不一致**——元件在网表里存在（仿真能跑），但绘图引擎拿不到有效的图形变换。

B 家的做法给了两条可试的路：

1. **骨架换成本机 COM 新建的空白工程**（不继承 sample 的旧格式骨架）；
2. **不要整体平移 symbol，而是先从 pin 几何反推符号中心，归一化后再定位**，文字单独处理。

---

## 5. 两家各自强在哪、怎么实现的

### A 家强的两点

**① SPICE 命令行路径做得比我们扎实。** `tool_run_spice` 里有一堆踩坑后的防御，我们没做：

- 临时文件放 `C:\mcp_spice_tmp`（根目录，避开用户名里的 `&` 和路径里的空格）
- `source` 命令用 **8.3 短路径**
- 网表强制 ASCII（`encode("ascii", errors="replace")`），因为 XSPICE 不吃多字节
- 预检必须以 `.end` 结尾
- 明确写进 tool description：节点电压用 `$out` 不能用 `v(out)`；XSPICE **不支持 `wrdata`**，只能 `print`

**② 把 API 的坑写进 tool description 给 Agent 看。** 这是给模型用的文档，不是给人看的——`suggested_recovery` 字段也是同理。

### B 家强的三点

**① 骨架来源"自证正确"。** 不信任安装包里的 sample（可能是旧格式），而是每次用 COM 新建空白工程现取骨架。

**② 验收是算出来的，不是写死的。** `ExperimentSpec` 里写

```json
{"metric":"gain","signal":"V(vout)","reference_signal":"V(vin)",
 "operator":"approximately","target":0.5,"tolerance_percent":1}
```



````
跑完自动出 `pass` / `fail` / `unverified`。**证据缺失时只给 `unverified`，不猜。**

**③ 隔离和恢复。** 32 位 worker + 心跳 + 取消 + 父死自杀 + 持久 job 队列。COM 崩了不拖垮 MCP server。

---

## 6. 对我们的直接结论

**能抄且该抄的（按性价比）：**

1. **骨架换源**（最高优先级，直接冲着 05 号图那个 bug 去）。用 `msc.Multisim()` 新建空白工程 SaveAs，取它的 XML 当骨架，再往里挂元件。改动小、可回退。
2. **三态验收**写进 v0.9.1 的 `acceptance.json`：`pass` / `fail` / `unverified`。截图项在 `screenshot.py` 收尾前**必须写 unverified**。
3. **验收算子版本化**：`approximately` + `tolerance_percent`，别写自然语言。
4. **`workspace_manifest` SHA-256**：20 行代码，给每个 case 的产物出哈希。

**不能抄的：**

- 别用 Pillow 自绘冒充原理图（A 家 `render_netlist_schematic` 就是干这个的，正是用户明令禁止的）。
- 别为了扩元件改用"通用载体符号"（B 家扩展族就是这么干的，README 自己写了）。
- 别现在就去堆工具数量。两家一个 61 一个 123，但 B 家真正跑通的还是那几个 `natural_*` 一次性案例。**工具多 ≠ 会设计。**

**我们自己独有的：**

- 真实 GUI 截图（`PrintWindow`）。两家都没有——A 家是 Pillow 自绘 + `GetCircuitImage`，B 家是 `GetCircuitImage` + SVG。这条线上只有我们在做。
- 零第三方依赖。B 家要 pywin32 + 32 位 Python + Node + npm 包 + 本地模板包五件套；我们纯标准库。

---

## 7. 复现方法

```bash
# 克隆
git clone --depth 1 https://github.com/Last-emo-boy/Multisim-MCP.git repoA
git clone --depth 1 https://github.com/yxy050208/multisim-mcp.git repoB

# A 家：只需要 pywin32（MCP 层在 32 位装不上，pydantic-core 没有 win32 wheel）
python demo_a.py            # 打开官方样本、枚举、导出、报错记录
python demo_a_spice.py      # SPICE 命令行 DC 扫描（这条能跑通）

# B 家
npm install --prefix ./nodecodec electronics-workbench-decoder@0.2.0
python run_bootstrap.py     # 生成 162 个模板文件
python demo_b.py            # 网表 -> XML -> .ms14
python demo_b_sim.py        # COM 跑瞬态，取波形数值
python run_transient_gui.py # 真 GUI 里跑瞬态分析，抓图示仪截图
````

脚本都在 `ref/` 下，输出在 `ref/out_a/`、`ref/out_b/`、`ref/artifacts/`。

> 注：A 家的 MCP 层在本机**装不上**——`mcp[cli]` 依赖 `pydantic>=2`，`pydantic-core` 没有 32 位 Windows wheel，而它的 COM 又必须 32 位。这是个架构矛盾，不是我的环境问题。所以我用它的 `com_adapter` 直连验证能力边界。
