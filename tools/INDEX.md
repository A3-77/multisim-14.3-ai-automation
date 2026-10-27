# tools/ 索引

这个目录里 `p*_*.py` 是**调查期的一次性脚本**，不是产品代码。
它们的作用是「证据」——每一条结论都能被重跑验证。别删。

## 先看这几个（产品代码 / 长期维护）

| 文件 | 作用 |
|---|---|
| `dcl.py` | PKWARE DCL 编解码 + `.ms14` 容器读写。零第三方依赖 |
| `mssafe.py` | **XML 无损往返**。保护属性值里的 `\r\n\t`，绕开 XML §3.3.3 归一化 |
| `msmodel.py` | 电路对象模型层（`Circuit` / 元件 / 引脚 / 网表） |
| `msbuild.py` | 装配器（从语料库克隆元件 + 连线 + 放探针）。`add_part()` 是统一入口 |
| `circuit_ir.py` | **Circuit IR 数据模型 + 校验**（纯 JSON，不含任何 XML 概念） |
| `ir_compile.py` | IR → `.ms14`（只调用已验证 API，落盘前先跑校验） |
| `ir_run.py` | IR 端到端验收（编译 → 仿真 → 拟合 → 与直接 API 基线比对） |
| `circuit_session.py` | **MCP 会话层**：circuit_id 句柄 / 语义参数映射 / 结构化错误 / 统一返回对象；布局委托给 `layout.py`（v0.7.0） |
| `layout.py` | **拓扑分析 + 坐标**（v0.7.0 P2 / v0.9 加一类）：`analyze()` 判断拓扑、`plan()` 生成坐标，两件事不混；支持单主干+到地并联（6 类模板）+ `halfwave_rectifier`（v0.9），其余明确拒绝 |
| `registry.py` | **元件注册表运行时读取层**（v0.9 新增）：纯 JSON，不碰 Multisim。`ir_spec(family, part)` 是**闸门**——只有 `enabled` 里的元件才返回 spec，其余一律 `None` |
| `build_registry.py` | **离线扫描器**（v0.9 新增）：扫 `corpus/samples14` + Multisim 官方样例，把每个元件的 `pins` / `pin_geometry` / `spice_template` / `donor` 抽成 `registry/components.json`。**零手写** |
| `mcp_server.py` | **MCP Server**（JSON-RPC over stdio，8 个工具；stdout 只走协议；schema 就是 Agent 的 API 文档。v0.9：`add_component` 描述从 `PART_META` 自动生成） |
| `mcp_client.py` | MCP 验收客户端：起子进程走真实协议，建 RC 与 DC 两个电路，真跑 Multisim |
| `agent_acceptance/` | **LLM Agent 测试台**：`mcp_stdio.py`（最小客户端）/ `agent_cli.py`（Agent 唯一入口，写 trace）/ `summarize.py`（trace→报告）/ `verify_sim.py`（从 CSV 独立复算）/ `run_diode.py`（v0.9 二极管端到端验收）。都不 import 项目模块 |
| `db_diag.py` | **元件数据库可用性诊断**（2026-10-27 新增）：快照环境 → 启动（`direct` 模拟双击 / `com` 模拟 v0.8）→ 轮询抓弹窗**全部控件原文** → 可选 Ctrl+W 实测元件库。产物 `out/dbdiag/<ts>_<tag>/{snapshot.json,timeline.jsonl,report.md,shots/}` |
| `db_cycle.py` | **数据库 A/B 循环压测**（同上）：每轮「清 `.ldb` 启动」+「留 `.ldb` 启动」各一次，打表统计成功率。用它证伪了「残留锁文件导致报错」的假设 |
| `db_cooldown.py` | **冷却期实验**（同上）：先拿到一次成功基线 → **正常关闭**（发 `WM_CLOSE`，不是强杀）→ 关闭后逐秒监控文件占用/`.ldb`/改动 → 等 `gap` 秒重开。用它证明了"关闭后 0–15s 必失败、60s+ 明显好转" |
| `test_mcp_session.py` | 会话层测试：113 项，不需要 Multisim（含 P2 拓扑、v0.8.0 的探针配对 / complete / start 校验） |
| `test_layout.py` | 拓扑层测试：51 项，纯逻辑。6 类模板 + 6 类拒绝 + 坐标性质 |
| `test_diode.py` | **v0.9 二极管闭环测试**：62 项，不需要 Multisim。registry 数据完整性 / IR 白名单合并 / 会话层 / 布局准入 / 编译 / 零回归 |
| `ir_sim.py` | 仿真 + 拟合内核（`nl_run` 用；`ir_run` 保持原样当基线，不被它影响） |
| `nl2ir.py` | **中文 → Circuit IR**（规则解析器，不依赖 LLM；产出前先 `validate()`） |
| `nl_run.py` | 中文端到端验收（一句话 → IR → `.ms14` → 仿真 → 理论比对） |
| `test_nl2ir.py` | 解析测试：59 项正向/反向用例，不需要 Multisim |
| `ir_compare.py` | 结构比对两个 `.ms14`（元件 / 主参数 / 网络成员 / 探针数） |
| `fitlib.py` | 正弦最小二乘拟合 + 一阶低通理论值 |
| `build_rc_lowpass.py` | 用 `add_part` 生成 RC 低通（`--freq` 改激励频率） |
| `validate_rc.py` | RC 瞬态验证：最小二乘拟合幅值/相位，和理论值比对 |
| `build_dc.py` | **最小直流电路** `V1→R1→GND`（只调已验证 API，出 `out/dc/dc_min.ms14`） |
| `dc_run.py` | **直流取数验收**（`--mode transient\|dcop`），docstring 里写死"`EnumOutputs` 只调一次" |
| `dc_strategies.py` | 直流取数时序实验 S1~S4（`--only` 单独跑；同一进程连跑会退化） |
| `build_acceptance.py` | 验收电路生成（默认源网探针；`--divider` 出分压器版） |
| `validate_acceptance.py` | 验收仿真 + 判定（读回电压/电流，比对期望值） |
| `test_mssafe.py` | 回归测试：4 个原生样本 XML 往返必须逐字节一致 |
| `test_ir.py` | Circuit IR 自检：结构 / params 类型 / JSON 往返 / 禁止出现 XML 概念 |
| `test_ir_validate.py` | IR 校验的 26 个反向用例（含"非法 IR 不得落盘"） |
| `p18_run2.py` | 稳健的瞬态读取模板（**必须在 `stop()` 之前 `read()`**） |

## 调查阶段对照表

| 阶段 | 脚本前缀 | 在查什么 | 结论落点 |
|---|---|---|---|
| 1–9 | `p1_*` `p2_*` `p6_*`–`p9_*` | `.ms12` 早期格式、7812 电源电路、探针克隆、基底裁剪 | `docs/ms14-format.md` |
| 11–13 | `p11_*`–`p13_*` | COM 接口探测、静态 XML 逐节点比对、RC 低通 | `docs/api.md`、`docs/deadends.md` |
| 14–16 | `p14_*`–`p16_*` | 波形读取时序、`V(pin)` 注入、符号属性/引脚类型比对 | `docs/probe.md` |
| 17 | `p17_*` | 探针与引脚普查：`NodeText`、junction、`PortID`、`ConnectList` | `docs/deadends.md` 三～五 |
| 18 | `p18_*` | **根因定位**：分离容器压缩 vs XML 往返，最终锁定 `CIITDiagram@SimState` | `docs/p0-acceptance.md`、`docs/deadends.md` 六 |
| 19 | `p19_*` | **探针唯一命名 + 元件定位锚点**：`LocalName` 序号决定 COM 输出名；`add()` 的 `anchor="pin"` | `docs/probe.md` 4.1 |
| 20 | `out/dc/bisect.py` | **COM 调用顺序**：P0~P4 逐个加一次调用，锁定"`run()` 之后 `EnumOutputs` 会作废输出缓冲" | `docs/dc-static.md` |
| 21 | `_scan_*` `_probe_*` `_rerun_rc.py` `_compare.py` | **14.3.3 升级后能力复测**：基线复算、donor 池扩容、二极管/NPN/运放端到端、COM 库接口探查 | `docs/v0.9-component-library-assessment.md` |
| 22 | `build_registry.py` `registry.py` `test_diode.py` `run_diode.py` | **v0.9 二极管闭环**（这轮不是调查，是产品化）：ComponentSpec 自动抽取 → IR 白名单 → 布局模板 → 真实仿真 → 独立复算 | `docs/v0.9-diode.md` |

### p18 里最关键的四支（想复现根因就看它们）

1. `p18_ladder.py` —— L1 控制实验。**原生文件原样过一遍保存路径**，电压还对但电流归零 ⇒ 写盘路径本身有损。
2. `p18_repack.py` —— 分离两个变量。只重打包容器（XML 字节不动）完好；裸 `ET` 往返就废。**这张表是判决书**。
3. `p18_xmldiff.py` —— 定位损坏点。行数 18769 → 11294，首个分叉正好在 `SimState="..."`。
4. `p18_divdc.py` / `p18_matrix.py` —— 修复后的阳性验证。纯电阻分压中点读 2.5 V。

### 第 21 轮（14.3.3 能力复测）的十支脚本

都是只读探查，**不改项目代码**，结论全部落在 `docs/v0.9-component-library-assessment.md`。

| 脚本 | 干什么 | 关键输出 |
|---|---|---|
| `_scan_pool.py` | 扫 corpus 的 donor 池，按 (family, part) 列来源 | 32 种 |
| `_scan_ext.py` | 强制触发 `find_part()` 的官方样例兜底（`msbuild.py:120`），再扫一遍 | **32 → 193 种** |
| `_probe_parts.py` | 对 11 种目标元件提取引脚名 / 参数 / SPICE 模板 / 图形 | `DIODE A,K`；`BJT_NPN B,C,E`；`MOS_ENH_N D,G,S`；`OPAMP/LM358AD 1IN+,1IN-,1OUT,VS+,VS-` |
| `_rerun_rc.py` | 升级后一阶 RC 复测，全程走 `agent_cli.py`（每次调用独立进程，等价 Agent 视角） | 14 次调用 0 错误，`simulate` 33.5 s / n=800 |
| `_compare.py` | v0.8 基线 vs 14.3.3 对账，含理论值 `fc=482.29 Hz`、`|H(1k)|=0.434405` | gain 差 **-0.003%** |
| `_probe_diode.py` | MCP 白名单验证 + 二极管半波整流端到端 | 通过；`max 4.3751 / min -0.0019 / mean 1.3061 V` |
| `_probe_3pin.py` | NPN 二极管接法 + 运放跟随器 | NPN 通过（`Vbe=0.6666 V`）；**运放未通过（`outputs=[]`）** |
| `_probe_com.py` | 枚举 `MultisimApp` / `Circuit` 的 COM 成员 | `MultisimApp` 16 个、`Circuit` 46 个，**零元件库接口** |
| `_probe_com2.py` | 同上的深挖版（注意要 `python -u`，否则输出被缓冲吞掉） | 库相关只有 `EnumComponents/EnumSections/EnumVariants/ReplaceComponent` |
| `_probe_replace.py` | 实测 `ReplaceComponent` 能否换元件 | **传 int 枚举后 Multisim 直接崩溃，无 traceback** |

跑这些脚本的前提：
- `_probe_com*.py` / `_probe_replace.py` 必须在项目根加 `sys.path.insert(0, ROOT)` 才能 `import msc`（`msc.py` 在根目录，不在 `tools/`）。
- 不要显式再调 `app.connect()`，`msc.Multisim.__init__(connect=True)` 已经 Connect 过，重复调必报 `拒绝访问`。
- `_probe_replace.py` 会让 Multisim 进程消失，**跑之前先确认没有别的东西挂在这个实例上**。

## 第 22 轮（v0.9 二极管闭环）

这一轮**不是调查**，是产品化。调查脚本一个没加，新增的全是产品代码 + 测试 + 验收台。
结论落在 `docs/v0.9-diode.md`。

| 文件 | 性质 | 干什么 |
|---|---|---|
| `build_registry.py` | 产品（离线工具） | 扫 128 个 `.ms14`（corpus 10 + 官方 118），抽出 192 种元件的 ComponentSpec，写 `registry/components.json`。耗时 ~2 min |
| `registry.py` | 产品（运行时） | 读 `registry/components.json`，`enabled_keys()` / `ir_spec()` / `donor_path()`。**闸门在这一层**，`circuit_ir` 和 `circuit_session` 都只问它 |
| `test_diode.py` | 测试 | 62 项，不需要 Multisim。含"5 种老元件行为不变"的硬断言（pins/aliases 逐字段比对） |
| `agent_acceptance/run_diode.py` | 验收 | Agent 视角端到端：8 段、14 次 MCP 调用、不 import 任何项目模块、从 CSV 独立复算 |

### registry 的两个字段必须分清

```jsonc
{
  "enabled": ["DIODE/1N4007G"],   // ← 闸门：Agent 能用的
  "parts": { "DIODE/1N4007G": {...}, "BJT_NPN/2N3904": {...}, ... }  // ← 扫到过的：192 条
}
```

`parts` 里有 192 条**不等于**支持 192 种。`parts` 只说明"donor 存在、引脚抽出来了"，
`enabled` 才是"IR 白名单 + 布局模板 + 测试"三样都齐了。加一种元件 = 三件事，不是改一行 JSON。

## 一次性脚本的用法

基本都是「打开某个 `.ms14` → dump 某一类对象 → 打印」。改脚本顶部的路径常量再跑即可。
输出一般落在 `out/`（已被 gitignore，只有 `out/ref/` 入库）。

## 注意

- 跑任何 COM 脚本前先 `taskkill /F /IM multisim.exe`，残留进程会导致读到空数据。
- 一个进程只开一个 `.ms14`。
- **`EnumOutputs()`（`circ.probes()`）只能在 open 之后调一次**。在 `run()` /
  `DoDCOperatingPoint()` 之后、`read()` 之前再枚举，会让之后所有 `GetOutputData()`
  返回 `E_FAIL`，表现像"电路死了"。见 `docs/dc-static.md`。
- 任何改动 `.ms14` 的代码，XML 读写必须走 `mssafe`，不要用裸 `ET.fromstring` / `ET.tostring`。
