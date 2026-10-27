# Multisim 14.3 元件数据库"时好时坏" — 调查报告

> 调查日期：2026-10-27
> 机器：`DESKTOP-LPI84MO`（Windows 11 专业版 25H2）
> 全程只读观察，未改注册表、未改配置、未删任何数据库文件。

---

## 0. 结论（先看这段）

**根因是版本与系统不匹配，不是数据库文件坏了、不是权限、不是残留锁文件。**

| 项 | 结论 |
|---|---|
| 数据库文件本身 | **好的**。`MSCOMP_S.PRD`（238 MB）存在、结构完好、可被 Jet 引擎识别 |
| 权限 / 磁盘 / 杀软 | **正常**，已逐项排除 |
| 残留 `.ldb` 锁文件 | **无关**，14 次 A/B 对照已证伪 |
| 真正的根因 | **Multisim 14.3.0 + 中文区域设置的 Windows 11**，属 NI 已知缺陷，**14.3.3 修复** |
| 本机版本 | `14.3.0.0`（`14.3.1482.0`）→ **低于修复版 14.3.3** |
| 复现失败率 | 14 次冷启动中 **11 次报错、3 次正常（≈79%）** |
| 修复 | NI Package Manager 升到 **Circuit Design Suite 14.3.3 或更高** |

**另外查出一个此前完全没记录的问题**：本机 Multisim 近 4 天崩了 **102 次**（10-24 52 次、10-26 30 次、10-27 17 次），全部是同一签名 —— `ucrtbase.dll` / `0xc0000409` / 子码 7。这是同一个"老版本跑在新系统上"的根因的另一张脸。

---

## 1. 第一阶段：环境事实

### 1.1 软件版本 —— 确认低于 14.3.3

| 来源 | 值 |
|---|---|
| `Multisim.exe` FileVersion | `14.3.1482.0` |
| `Multisim.exe` ProductVersion | **`14.3.0.0`** |
| `ultiboard.exe` | `14.3.1482.0` / `14.3.0.0` |
| NI Package Manager 包 `ni-cds-2014-core` | **`14.3.0.49153-0+f1`** |
| 注册表卸载项 `NI Circuit Design Suite 14.3 Core` | `14.30.49153` |
| 编译日期 | 2022-04-22 |

> NI 官方修复版是 **14.3.3**。本机是 **14.3.0**，差 3 个补丁版本。

NI 下载页确认 14.3 系列提供 `14.3.3 / 14.3.2 / 14.3.1 / 14.3.0` 四个版本，说明 14.3.3 可直接获取。

### 1.2 Windows 与区域设置 —— 命中已知故障条件

| 项 | 值 | 判定 |
|---|---|---|
| 系统 | Microsoft Windows 11 专业版 | — |
| 版本 | 25H2，Build **26200.9457** | 远新于 14.3.0 的发布年代 |
| **系统区域 (GetSystemDefaultLCID)** | **`2052` = 中文(简体，中国)** | ⚠️ **命中** |
| 用户区域 | `zh-Hans-CN` | ⚠️ 命中 |
| Culture / UICulture | `zh-CN` / `zh-CN` | ⚠️ 命中 |
| OEMCP / ACP | `936` / `936` | 中文代码页 |
| `Get-HotFix KB5065426` | 未找到 | 见下 |

**关于 KB5065426**：`Get-HotFix` 查不到是正常的 —— 该补丁是 2025 年 9 月针对 Windows 11 24H2 的累积更新，你的系统已经是 **25H2 / 26200**，它早已并入更晚的累积更新里。**KB5065426 不是"没装"，而是"装过了、并且被后续更新继承"**。

关键点在于：NI 那篇 KB 描述的是**故障机理**（Windows 更新改变了"区域设置为中文时"数据库相关 DLL 的行为），不是"必须精确存在这个 KB 编号"。你的机器**同时满足机理的两个条件**：中文区域 + 新版本 Windows。

**最硬的旁证**：崩溃报告里 `DynamicSig[2] 区域设置 ID = 2052`。这是 Windows 自己记录下来的、崩溃发生时的进程区域设置，不是我推断的。

### 1.3 数据库文件 —— 都在，而且都是完好的 Jet 库

`C:\ProgramData\National Instruments\Circuit Design Suite\14.3\database\`

| 文件 | 字节 | 修改时间 | 说明 |
|---|---|---|---|
| `MSCOMP_S.PRD` | **249,729,024**（238 MB） | 2022-03-22 07:45 | **主数据库（Master）** |
| `CPCOMP_S.PRJ` | 583,680 | 2026-10-27 12:32 | 企业数据库（Corporate） |

`%APPDATA%\National Instruments\Circuit Design Suite\14.3\database\`

| 文件 | 字节 | 修改时间 | 说明 |
|---|---|---|---|
| `UsrComp_S_A377.usr` | 544,768 | 2026-10-27 12:32 | 用户数据库（User） |

`C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3\database\`

| 文件 | 字节 | 说明 |
|---|---|---|
| `UsrCompTemplate_S.usr` | 544,768 | 用户库模板（你之前看到的 `UsrCompTemplate_S` 在这里，**不在 ProgramData**） |

**三个库的文件头全部是 `00 01 00 00 "Standard Jet DB"`** —— 都是合法的 Jet 4.0 数据库。

用 ADO/Jet 直接打开时返回 **`Not a valid password.`**（而不是 `Unrecognized database format`），说明：
- 文件结构**完好**，Jet 能正确解析头部；
- NI 给这些库加了密码，所以外部工具读不了内容 —— 这是**设计如此**，不是故障。

**关于 `Master_Database.mcdb`**：全盘搜索 `*.mcdb`、`*.prd`、`*.usd`、`*.ldb`，只找到上面这些。`.mcdb` 是 **Multisim 14.0/14.1** 时代的命名，**14.3 用的是 `.PRD`**。所以"找不到 `Master_Database.mcdb`"完全正常，不代表缺库。

### 1.4 Jet 引擎 —— 完好

| 项 | 值 |
|---|---|
| 注册表 `HKLM\SOFTWARE\WOW6432Node\Microsoft\Jet\4.0` | 存在，含 `Engines` / `ISAM Formats` / `Transporter` |
| `Engines\Jet 4.0` 参数 | `MaxLocksPerFile=9500`、`PageTimeout=5000`、`LockRetry=20` 等，**均为标准值** |
| `msjet40.dll` | `C:\Windows\SysWOW64\msjet40.dll`，版本 `10.0.26100.9278` |
| `dao360.dll` | `C:\Program Files (x86)\Common Files\Microsoft Shared\DAO\dao360.dll`，崩溃时已加载 |
| `msjtes40.dll` / `mswstr10.dll` / `expsrv.dll` | 崩溃时均已加载 |

→ **不是 KB1 描述的那种"Jet 注册表被第三方软件改坏"**。

### 1.5 权限 —— 正常

```
C:\ProgramData\...\14.3\database
  NT AUTHORITY\Authenticated Users   Allow  FullControl
  NT AUTHORITY\SYSTEM                Allow  FullControl
  BUILTIN\Administrators             Allow  FullControl
  BUILTIN\Users                      Allow  ReadAndExecute, Synchronize
  BUILTIN\Users                      Allow  Write
```
实测当前用户**可写**。用户库目录 `%APPDATA%\...\database` 对 `A377` 是 FullControl。

### 1.6 磁盘与杀软 —— 排除

| 项 | 值 | 判定 |
|---|---|---|
| 磁盘 | Great Wall GW3300 1TB **SSD (NVMe)** | — |
| 读 238 MB 主库 | 0.28 s / 0.10 s / 0.10 s（846→2377 MB/s） | 不是 I/O 超时 |
| 杀毒软件 | 仅 Windows Defender，实时保护开启 | 无第三方杀软干扰 |
| 受控文件夹访问 | `EnableControlledFolderAccess = 0`（关闭） | 不拦截 |

### 1.7 崩溃日志 —— 102 次，同一签名

Windows 应用程序日志（Event ID 1000 / 1001）统计：

| 日期 | 崩溃次数 |
|---|---|
| 2026-10-23 | 3 |
| 2026-10-24 | 52 |
| 2026-10-26 | 30 |
| 2026-10-27 | 17 |

**完全一致的签名**：

```
出错应用程序名称: Multisim.exe，版本: 14.3.1482.0，时间戳: 0x6262d5a9
出错模块名称:     ucrtbase.dll，版本: 10.0.26100.9444，时间戳: 0x80cf5d8f
异常代码:         0xc0000409
异常数据 (P9):    00000007        ← FAST_FAIL_FATAL_APP_EXIT（CRT abort / std::terminate）
错误偏移:         0x0002da71
事件类型:         BEX
Bucket:           52dd7febc0ea16391d32bfefd4a31561   （所有崩溃同一个桶）
区域设置 ID:      2052
OS 版本:          10.0.26200.2.0.0.256.48
```

进程存活时长：**2.0 – 9.5 秒**，即崩溃发生在**启动阶段**（闪屏 → 库加载之间），不是退出时。

崩溃时已加载 238 个模块，其中关键的有：

```
[137] Database.dll          ← 元件数据库访问
[155] LibMng.dll            ← 库管理
[158] ub_db_convert.dll
[220] dao360.dll            ← DAO
[222] MSJET40.DLL           ← Jet 4.0 引擎
[223] mswstr10.dll
[225] expsrv.dll            ← Jet 表达式服务（对区域敏感）
[228] msrd3x40.dll
[229] msjtes40.dll          ← Jet Expression Service
[230] VBAJET32.DLL
```

→ Jet 栈**加载成功**，崩溃发生在之后的初始化环节，且**崩溃点恒定**（同一个偏移、同一个 Bucket）。这说明它不是一个"随机竞态"，而是**每次都在同一处失败**，只是有些启动中异常被捕获（弹窗后继续跑），有些没被捕获（CRT abort）。

---

## 2. 第二阶段：复现记录

### 2.1 完整报错原文

**中文原文（弹窗标题 `Multisim`）**：

```
确认(&O)

访问数据库时发生错误。

主数据库 无法访问。使用 主数据库 的功能将不可用。
```

截图：`out/dbdiag/20261027-133821_A2_staleldb/shots/dlg_2_133825.png`

**对应 NI KB 的英文原文**：

```
Problem: Accessing the database.

The Master Database cannot be accessed. Features using the Master Database
will not be available.
```

→ **一字不差**，就是 NI KB `kA00Z0000019YLUSA2` 和 `kA0VU000000DreP0AS` 描述的那个弹窗。

**补充观察**：本机每次都只弹 **主数据库（Master）** 一个框，点确定后不再连环弹 Corporate / User。NI KB 提到"有时还会接连跳出 Corporate 和 Master"—— 说明不同机器表现略有差异，但根因相同。

### 2.2 启动方式对照

| 启动方式 | 表现 |
|---|---|
| **direct**（`Popen(Multisim.exe)`，等价双击） | 有可见 UI；约 4.9 s 时弹数据库报错框 |
| **com**（`Dispatch("MultisimInterface.MultisimApp")` + `Connect()`，即 v0.8 的方式） | **全套窗口都建好了，但 `vis=0` 全部不可见**；没有任何可见弹窗 |

COM 实例的窗口清单（实测，全部 `vis=0`）：

```
cls=Multisim14.3   title='Multisim 14.3'      rect=(179,179,1331,771)
cls=#32770         title='选择一个元器件'       rect=(201,66,882,606)
cls=#32770         title='仿真错误记录信息窗口'
cls=#32770         title='EWB Debug Log'
...
cls=LVFrame        title='multisim'  vis=1  rect=(0,0,0,0)   ← 唯一"可见"的，但是零尺寸
```

**这解释了一个关键疑问**：v0.8 用 COM 启动时，数据库报错**即使发生了也看不见**（弹窗是隐藏的），而且 v0.8 根本不依赖数据库，所以从未暴露。

### 2.3 失败率与 A/B 对照（关键实验）

**假设 H1：残留 `.ldb` 锁文件导致数据库打不开。**

如果 H1 成立，那么"清掉 `.ldb` 就一定能成功"。实测：

| 轮次 | A 组（先清 `.ldb`） | B 组（保留残留 `.ldb`） |
|---|---|---|
| 批次 1-1 | **DB_FAIL** | DB_FAIL |
| 批次 1-2 | **DB_FAIL** | DB_OK |
| 批次 1-3 | **DB_FAIL** | DB_FAIL |
| 批次 2-1 | **DB_FAIL** | DB_FAIL |
| 批次 2-2 | **DB_FAIL** | DB_OK |
| 批次 2-3 | **DB_FAIL** | DB_FAIL |
| 批次 2-4 | **DB_FAIL** | DB_OK |

**汇总：A 组（清锁）成功 0/7，B 组（留锁）成功 3/7。**

→ **H1 被证伪**。`.ldb` 的有无与成败**完全无关**，甚至清了反而更容易失败（统计上无意义，说明就是随机）。

**总采样：14 次冷启动，11 次报错、3 次正常 ≈ 79% 失败率。**

### 2.4 已排除的因素汇总

| 怀疑项 | 检验方法 | 结果 |
|---|---|---|
| 数据库文件缺失 | 全盘搜索 `*.prd` / `*.mcdb` / `*.usr` / `*.prj` | ❌ 排除，文件都在 |
| 数据库文件损坏 | Jet 直接打开，看错误类型 | ❌ 排除，报 `Not a valid password`（结构完好） |
| 权限不足 | 读 ACL + 实测写文件 | ❌ 排除，Authenticated Users 有 FullControl |
| 磁盘慢 / I/O 超时 | 计时读 238 MB | ❌ 排除，0.1 s |
| Jet 注册表损坏 | 读 `WOW6432Node\...\Jet\4.0\Engines\Jet 4.0` | ❌ 排除，参数全标准 |
| 第三方杀软 | 查 SecurityCenter2 | ❌ 排除，仅 Defender |
| 受控文件夹访问 | `Get-MpPreference` | ❌ 排除，已关闭 |
| 残留 `.ldb` 锁 | 7 轮 A/B 对照 | ❌ **证伪** |
| 多实例互相抢占 | 每次实验前 `taskkill` 清空，实测始终单实例 | ❌ 排除 |
| 用户配置损坏（KB1 第 2 条） | 查 `config\standard_ms_pro.ewcfg` | ❌ 排除，是今天自动生成的正常文件 |
| 数据库路径配错（KB1 第 1 条） | 文件都在默认路径，且今天被 Multisim 正常写入 | ❌ 排除 |

### 2.5 唯一剩下的解释

**中文区域 + 新版 Windows 的数据库相关 DLL 行为异常，导致 Jet 打开库时抛异常。**

证据闭环：

1. 故障**只在启动加载库时**发生（4.9 s 那个时间点，正好是 `Database.dll` 之后）；
2. 崩溃报告的 `区域设置 ID = 2052`，是系统自己记的；
3. 崩溃点**恒定**（同一偏移 `0x2da71`、同一 Bucket），说明是确定的代码路径失败，不是随机内存踩踏；
4. **与 `.ldb`、权限、磁盘、文件完整性全部无关**（已逐项排除）；
5. 失败率 ≈79% 而非 100%，符合"异常被捕获/未被捕获"两种走向 —— 被捕获就弹框，没被捕获就 `abort` 崩溃；
6. NI 官方明确写了这个机理，并明确说 **14.3.3 修复**。

---

## 2.6 补充实验（2026-10-27 14:20–14:50）：确实与"关闭后经过的时间"有关

用户反馈："打开没弹窗（库可用）→ 关闭 → 接着打开就弹窗 → 过一段时间再打开又没弹窗了。"

这个观察**成立**，而且我前面用 `taskkill /F` 强杀的实验**掩盖了它** —— 强杀和正常关闭对资源的释放路径不同。

### 实验结果

| 关闭后等待 | 重开结果 | 备注 |
|---|---|---|
| **0 s** | **DB_FAIL ×2** | 正常关闭后立刻重开 |
| **2 s** | **DB_FAIL ×4 / DB_OK ×1 / DB_FAIL** | 连开 6 次，只中 1 次 |
| **15 s** | **DB_FAIL** | |
| **60 s** | **DB_OK** | |
| **90 s** | **DB_FAIL** | ← 说明不是硬阈值 |
| **90 s + 先自己读完 238 MB 主库** | **DB_OK** | |
| **180 s** | **DB_OK** | |

**结论：短间隔（0–15 s）几乎必失败，长间隔（60–180 s）成功率明显上升，但不是"到点就恢复"的硬阈值。**

### 冷却期里到底有什么在占着？—— 全部排除

关闭后连续监控 100 秒（每 2 秒一次）：

```
  t(s) PRD空闲   PRJ空闲   USR空闲   .ldb   文件改动
   0.0  True     True     True      无     -
   ...
 100.1  True     True     True      无     -
```

- 三个数据库文件**从 t=0 起就能被独占打开**，全程没有进程持有句柄
- **没有 `.ldb`** 生成
- 100 秒内**没有任何文件被改写**

→ 所以冷却期**不是"文件锁没释放"、不是 `.ldb` 残留、不是关闭时重写了库文件**。

### 一个必须纠正的认知

检查事件日志发现：**每一次"正常关闭"其实都是一次崩溃**。

```
14:39:08  存活=14.2s
14:39:28  存活=14.2s
14:41:58  存活=14.1s
14:42:20  存活=14.1s
14:42:42  存活=14.1s
14:43:04  存活=14.1s
```

"存活 14.1 秒"精确等于"我发 `WM_CLOSE` 的时刻" —— 说明进程不是优雅退出，是收到关闭消息后在 `ucrtbase` 里 `abort` 了。

**所以更准确的描述是**：每次退出 Multisim 都会触发一次 `0xc0000409` 崩溃；崩溃之后的一小段时间内再启动，数据库打开会失败；等 NI 运行时/WER 的收尾走完，才恢复正常。

这仍然不是"锁"层面的问题（文件全程可独占），而是**进程外残留状态**的问题。

### 尚未确定的部分

冷却期的**精确长度**和**确切机制**还没锁定：

- 60 s 和 180 s 各成功 1 次，但 90 s 失败过 1 次 —— 样本太小，只能说"约 1–2 分钟后成功率明显上升"；
- 尚未确认是 Windows Error Reporting 的转储收集、还是 NI 某个常驻服务（`nisvcloc` / `nidmsrv`）的会话回收、还是 Multisim 自身在退出时写坏了某个运行时状态；
- 因为根因已经明确（版本缺陷，14.3.3 修复），继续深挖机制对**解决问题**没有额外收益。

### 实用建议

1. **关掉 Multisim 后等 1–2 分钟再开**，别连点；
2. 连开 3 次都弹窗 → 说明还在冷却窗口里，继续等，别反复点；
3. 某次开成功了就**别关**，把活干完；
4. 根治仍然是升级 **14.3.3**。

---

## 3. 修复方案

### 方案 A（推荐）：升级到 14.3.3 或更高

这是 NI 官方给出的唯一根治方案。

1. 打开 **NI Package Manager**
2. 切到 **更新** 选项卡
3. 勾选 **Circuit Design Suite**，执行更新到 **14.3.3+**
4. 更新完重启，再打开 Multisim 验证

> 你的 `NI Package Manager` 是 `21.3.0 / 21.30.49256`，支持这个更新路径。
> 若"更新"页没有列出，改到 **浏览产品** 搜 `Circuit Design Suite`，版本选 14.3 及以上重装。

### 方案 B（不能升级时的绕过）：改系统区域设置

NI KB 明确给了这条绕过方案：

1. 控制面板 → **时钟和区域** → **区域**
2. **管理** 选项卡 → **更改系统区域设置**
3. 当前区域从「中文(简体，中国)」改为 **英语(美国)**
4. **不要勾选**「Beta: 使用 Unicode UTF-8 提供全球语言支持」
5. 重启电脑

⚠️ **重要限制**（NI 原文）：对于**中文原生版本**的 Windows 11，**只改"显示语言"是无效的**，必须改**系统区域设置（System Locale）**。改完副作用是部分老软件的中文路径/编码可能出问题。

### 方案 C（应急，不推荐长期用）

失败率 79%，意味着**平均重开 4–5 次能碰上一次成功**。应急可以：
- 关掉 Multisim → 重开 → 看有没有弹框 → 有就再关再开
- 一旦某次没弹框、元件库正常，**这次就别关**，把活干完

### 不要做的事

| 别做 | 原因 |
|---|---|
| 删 `config` 目录里的文件（KB1 第 2 条） | 你的 config 是正常的（2022 原版 + 今天自动备份），删了只会丢偏好设置 |
| 重装/改 Jet 注册表（KB1 第 3 条） | 你的 Jet 注册表是标准值，没坏 |
| 删 `.ldb` | 已证伪，没用 |
| 重装整个 Multisim 14.3.0 | 还是 14.3.0，装完照样坏。**要装就装 14.3.3+** |
| 只改显示语言 | NI 明确说对中文原生 Windows 11 无效 |

---

## 4. 对 v0.8 / 本项目的影响

**结论：不影响。v0.8 不需要数据库。**

但要把因果关系说清楚，避免以后误判：

1. v0.8 的元件来自 `corpus/samples14/*.ms14` 的 donor 深拷贝，SPICE 模板和符号图形都内嵌在 `.ms14` 里 —— 出网表和显示都不查库。
2. v0.8 走 COM 启动，Multisim 实例**无可见 UI**，数据库报错**即使发生也看不见**，且不影响 `OpenFile` + 仿真。
3. 所以：**"数据库坏了但 v0.8 还能跑"不是巧合，是设计上就不依赖。**

**但有两个真实风险需要记住**：

| 风险 | 说明 |
|---|---|
| `corpus/samples14/` 是硬依赖 | 删了它整套系统就废，且只能用 donor 里出现过的型号 |
| Multisim 崩溃 | 崩溃发生在启动阶段（2–10 s），如果正好撞上仿真窗口，会导致仿真失败。目前 11 次真机仿真都成功了，但这个风险客观存在 |

**建议**：把"Multisim 崩溃"纳入 v0.8 的错误处理 —— `simulate` 失败时先看事件日志有没有新的 `ucrtbase / 0xc0000409`，有就自动重试一次，而不是直接报"仿真失败"。

---

## 5. 本次新增的诊断工具

为这次调查新写了两个工具，都只读、可重复跑：

### `tools/db_diag.py` —— 单次启动诊断

```bash
# 模拟双击启动，抓弹窗原文 + 截图
python tools/db_diag.py --tag cold1 --mode direct --wait 25 --auto-ok

# 模拟 v0.8 的 COM 启动
python tools/db_diag.py --tag com1 --mode com --wait 20

# 顺便按 Ctrl+W 实测元件库能不能打开
python tools/db_diag.py --tag lib1 --mode direct --ctrlw

# 启动前清 .ldb（本次实验用的开关）
python tools/db_diag.py --tag clean1 --clean-ldb
```

产物：`out/dbdiag/<时间戳>_<tag>/`
- `snapshot.json` —— 版本、区域、三个库的大小/时间/哈希、`.ldb` 前后状态、Jet 注册表、进程
- `timeline.jsonl` —— 逐事件时间线（启动 / 弹窗 / 主窗口 / 进程消失）
- `report.md` —— 人读报告，带 `DB_OK` / `DB_FAIL` / `NO_UI` 判定
- `shots/*.png` —— 弹窗截图 + 全屏截图

### `tools/db_cycle.py` —— A/B 循环压测

```bash
python tools/db_cycle.py --rounds 4 --wait 11
```

每轮固定跑「清 `.ldb` 启动」+「留 `.ldb` 启动」，最后打表统计成功率。本次就是靠它证伪了 `.ldb` 假设。

---

## 6. 附：判定依据速查

| 你的问题 | 答案 | 依据位置 |
|---|---|---|
| 版本是否低于 14.3.3 | **是**，14.3.0.0 | `Multisim.exe` ProductVersion + `ni-cds-2014-core 14.3.0.49153` |
| Windows 版本 | 11 25H2 / 26200.9457 | `Get-CimInstance Win32_OperatingSystem` |
| 系统区域 | **zh-CN (2052)** | `Get-WinSystemLocale` + WER `区域设置 ID` |
| 是否符合 NI 故障条件 | **符合** | 中文区域 + 新 Windows + CDS < 14.3.3 |
| 数据库路径 | 默认路径，正确 | 三处目录全部实存且被写入 |
| 数据库文件 | 3 个，完好 | 文件头 `Standard Jet DB`，Jet 返回 `Not a valid password` |
| 配置文件 | `%APPDATA%\...\config\standard_ms_pro.ewcfg` | 今天自动生成 + `.backup` |
| 进程启动方式 | direct / COM 两种都已测 | COM 实例全窗口 `vis=0` |
| 权限 | 正常 | ACL + 实测可写 |
| 事件日志 | 102 次崩溃，同一签名 | Event 1000/1001 |
| Multisim 自有日志 | **没有**（只有 `EWB Debug Log` 窗口，非文件） | 全盘搜 `*.log/*.txt/*.err` 无结果 |
| 多实例 | 不存在，始终单实例 | 每轮 `tasklist` 校验 |
| `MSComp_S.prd` 其他位置 | 只有一处 | 全盘搜索 |
| `Master_Database.mcdb` | **14.3 不存在此文件**（旧版命名） | 全盘搜索 `*.mcdb` 零结果 |
| 完整报错文字 | 见 §2.1 | 截图 + 控件文本 dump |
| 能否搜索/放置元件 | **不能**（主库不可用时库为空） | 与 NI KB 描述一致 |
