# Multisim 14.3 AI 自动化 —— 逆向工程报告

> ## ✅ v0.2.0（2026-10-26）：找到并修掉真正的根因
>
> **根因：`CIITDiagram@SimState` 属性里存着多行仿真状态文本，XML 规范要求
> 解析时把属性值里的换行归一化成空格，`xml.etree.ElementTree` 照做 →
> 仿真配置被压平 → Multisim 读不回分析设置 → 只剩电源在动，R/C 全部开路。**
>
> 表现就是长期被误判成「克隆的电阻是开路的」的那个现象：电源电压还在、
> 电阻电流恒 0、部分输出读不出来。
>
> 三行证据（同一份原生文件，逻辑零改动）：
>
> | 版本 | V(PR1) | I(PR1) | 可读输出 |
> | --- | --- | --- | --- |
> | 原生 | 84 V | **13.9977 A** | 8/8 |
> | 只重打包容器（XML 字节不动） | 84 V | **13.9977 A** | 8/8 |
> | 仅 ET 解析 + 序列化 | 84 V | **0 A** | 3/8 |
>
> 修复：新增 `tools/mssafe.py`，解析前把属性值内部的 `\r\n\t` 换成 ASCII
> 占位符，序列化后还原；`msmodel.Circuit` 的读写全部改走它。
> 回归测试 `tools/test_mssafe.py`：4 个原生样本往返**逐字节一致**。
>
> ### 验收结果（全部实测，非推断）
>
> | 用例 | 期望 | 实测 | 结论 |
> | --- | --- | --- | --- |
> | `out/ref/acceptance.ms14`（探针在源网） | 5.0 V 恒定 | **5.0 V**，极差 1.8e-15，2000 点 | ✅ |
> | `out/ref/acceptance_divider.ms14`（探针在分压中点） | 2.5 V 恒定 | **2.5 V**，极差 1.3e-15，2000 点 | ✅ |
> | `RLCValue('R1')` | 1000 Ω | **1000.0 Ω** | ✅ |
>
> **分压器中点读到 2.5 V，是电阻真的在导通的直接证据**——这正是 v0.1.0 里
> 缺的那一环。探针在源网只证明电源在，中点 2.5 V 才证明 R1/R2 进了 SPICE 网表。
>
> 同时被证伪的几个假设（详见 `docs/deadends.md`）：
> `CIITLinkComp@NodeText` / `CODNodeTextComp` 网络分组、`CODPinComp` 交汇结点
> （junction）、`CSCH_CAPVirtualComponentPin@lastnet`、`CIITPinSymbolComp@PortID`
> 重复、虚拟元件缺 `Model` 属性、`doubles` 与 `parameters` 布局、供体文件损坏。
> **这些都不是原因。** 3 引脚中点不需要任何结点对象，实测 2.5 V。
>
> 验证记录：[`docs/p0-acceptance.md`](docs/p0-acceptance.md) ·
> JSON：[`out/p0_validation.json`](out/p0_validation.json) ·
> 波形：[`out/p0_waveform_source.csv`](out/p0_waveform_source.csv)、
> [`out/p0_waveform_divider.csv`](out/p0_waveform_divider.csv)
>
> ---
>
> **一句话结论：从空白电路用代码生成 `.ms14`，Multisim 能打开、能真实仿真、
> COM 能读到正确读数——含分压器这种需要多个无源元件真正导通才能成立的拓扑。**

本仓库是完整的过程记录 + 可运行代码 + ground truth 语料库，供后续 agent 接手继续研究。

---

## 目录

| 文档 | 内容 |
| --- | --- |
| [docs/ms14-format.md](docs/ms14-format.md) | **`.ms14` 文件格式完整规范**：PKWARE DCL 压缩算法 + 分块容器 + 字节级细节 |
| [docs/circuit-xml.md](docs/circuit-xml.md) | **电路 XML 对象模型**：两棵平行树、坐标系、引脚几何公式、参数存储位置 |
| [docs/probe.md](docs/probe.md) | **探针**：结构、网络绑定方式、GUI 放置流程（已跑通） |
| [docs/architecture.md](docs/architecture.md) | 代码架构与每个文件的职责 |
| [docs/deadends.md](docs/deadends.md) | **死路清单 + 避坑指南**（必读，能省几十小时） |
| [docs/next-steps.md](docs/next-steps.md) | **给接手者的路线图**：按优先级排好的待办 |

---

## 一、任务演进（为什么要做这件事）

用户的原始诉求分三个阶段，约束越来越严：

1. **阶段一**："看看能不能编程操控本机 NI Multisim 14.3，GitHub 有现成的就直接用。"
   → 结论：GitHub 没有可用项目。做出了 COM API 封装（`msc.py`），能跑仿真、取波形、导 CSV。
2. **阶段二**：用户明确否定了"只能跑"的成果——
   > "为什么这么多不能的，如果只能跑的话那也不叫 ai 自动化啊 我自己也会跑啊"

3. **阶段三（当前目标，死标准）**：
   > **"不要把'能够修改已有电路'视为任务完成。必须实现'从空白电路开始，根据自然语言指令
   > 创建一个全新的、可被 Multisim 正常打开和仿真的电路。"**

   验收用例：
   > "新建一个 5V 直流电源串联 1kΩ 电阻接地的电路，在电阻两端放电压探针并保存。"

   > **"不要让 AI 把'找到 API'当成果，要把'生成一个全新的、能在 Multisim 里打开的真实电路'
   > 作为唯一的核心验收标准。"**

**当前进度：验收用例已完成约 85%。**

| 验收点 | 状态 | 证据 |
| --- | --- | --- |
| 从空白电路开始 | ✅ | `out/ref/blank_circuit.xml` 是空白基底，注入后 `own_blank.ms14` 能正常打开 |
| 5V 直流电源 | ✅ | `acceptance.ms14` 里 V1，XML 值 `5.`，界面显示 `5V` |
| 串联 1kΩ 电阻 | ✅ | R1，XML 四处值全同步，界面显示 `1kΩ`（见 `docs/shots/03_*.png`） |
| 接地 | ✅ | GND 符号克隆自官方样例，正常渲染 |
| 可被 Multisim 正常打开 | ✅ | 免提权启动 + 自动点弹窗 + 截图，见 `docs/shots/01_*.png` |
| 电压探针 | 🟡 半完成 | GUI 路线已跑通（能放、能存）；纯代码路线结构已摸清，未实现 |
| 可仿真 | ⬜ 未做 | 代码已就绪（COM API），未在自建电路上跑过 |

---

## 二、三条技术路线与结论

### 路线 A：NI 官方 COM Automation API（`MultisimInterface.MultisimApp`）

**能做**：打开/保存、枚举元件、读改 R/L/C 值、跑瞬态/交流/直流分析、取波形数据、导 CSV/BOM/网表、截图。

**不能做**：**放元件、拉导线、加探针**。整个 API 没有这类方法（只有 `ReplaceComponent`）。

**结论**：保留为"仿真执行层"。等电路文件生成好之后，用 COM 去跑仿真、取数——这是最省事的方案，
不需要逆向仿真引擎。

关键坑：
- **必须 32 位 Python**。CLSID `{D9CBB7A1-6AD6-438B-AD1B-42FB2DB00CAE}` 只注册在 WOW6432Node，
  64 位进程 `CreateObject` 直接报"没有注册类"。
- **探针 = 输出**。`EnumOutputs()` 枚举的是图纸上的探针（`V(Probe1)` 这种名字），
  没探针就取不到数据，报错是"输出未找到。"——**所以探针是仿真取数的前置条件**，
  这也是为什么探针必须做。

代码：`msc.py` / `cli.py` / `demo.py` / `docs/api.md`（从类型库导出的 40+ 方法全表）。

### 路线 B：逆向 `.ms14` 文件格式（**主线，已突破**）

`.ms14` 是一个自定义压缩容器，载荷是电路 XML。破解后可以直接用代码生成/修改电路文件，
不依赖 Multisim 运行。**这是唯一能实现"从零画电路"的路线。**

详见 [docs/ms14-format.md](docs/ms14-format.md)。

### 路线 C：GUI 自动化（兜底，部分跑通）

当某功能纯代码暂时做不出来时，用 Win32 消息驱动 Multisim 界面完成操作（例如放探针），
再让 Multisim 自己保存文件，然后解析保存结果反推结构。

**这条路线在本项目里发挥了关键作用**：探针的 XML 结构就是这么做出来的——
GUI 放一个探针 → 保存 → 解压 → 读 XML → 得到精确的对象结构。

详见 [docs/probe.md](docs/probe.md)。

---

## 三、当前可运行的能力

### 3.1 从零生成电路（纯代码，已验证）

```bash
cd multisim-ctrl
python tools/build_acceptance.py      # 生成 out/ref/acceptance.ms14
python tools/verify_open.py out/ref/acceptance.ms14 out/verify.json   # 启动 Multisim 打开并截图
```

产物 `out/ref/acceptance.ms14`（23897 字节）在 Multisim 里显示为：
V1(5V) — R1(1kΩ) — GND，三条导线，拓扑正确，参数显示正确。

### 3.2 编解码 `.ms14`（纯 Python，无第三方依赖）

```python
import sys; sys.path.insert(0, "tools")
import dcl

xml, info = dcl.read_ms14("out/ref/acceptance.ms14")   # 解压 -> 明文 XML
print(info)   # {'total': 209101, 'chunks': 1, ...}
dcl.write_ms14("out/copy.ms14", xml)                   # 重新打包，Multisim 认
```

压缩率实测：148367 B → 16272 B（Multisim 自己是 14481 B，我们慢 12%，但完全可用）。

### 3.3 驱动 Multisim GUI 放探针

```python
import sys; sys.path.insert(0, "tools")
import msui, guiauto as G

h = msui.launch("out/ref/with_probes.ms14")   # 启动 + 点掉 3 个数据库弹窗
G.click(178, 43)                              # 绘制 菜单
G.click(200, 85)                              # Probe 子菜单
G.click(427, 87)                              # 电压探针
G.click(725, 436)                             # 点到目标网络上
```

保存后文件里确实多了探针对象（`CiProbeExtComp`）。

### 3.4 统一元件 API + RC 低通（第二个验收案例，已通过）

`Assembler.add_part(family, part, refdes, value=, x=, y=, params=)`
按 `(family, part)` 从真实 `.ms14` 里找模板并克隆，**调用方不碰任何 XML ID**。

```python
import msbuild
a = msbuild.Assembler()
v1, _ = a.add_part("SIGNAL_VOLTAGE_SOURCES", "AC_VOLTAGE", "V1",
                   value=1.0, x=300, y=300, params={5: 1000.0})  # 1V / 1kHz 正弦
r1, _ = a.add_part("RESISTOR",  "RESISTOR_VIRTUAL",  "R1", value=1000.0, x=500, y=300)
c1, _ = a.add_part("CAPACITOR", "CAPACITOR_VIRTUAL", "C1", value=159e-9, x=700, y=400)
gnd,_ = a.add_part("POWER_SOURCES", "GROUND", "0", x=300, y=420)

n_in  = a.connect([(v1, "1"), (r1, "1")], name="in")
n_out = a.connect([(r1, "2"), (c1, "1")], name="out")
n_gnd = a.connect([(v1, "2"), (gnd, "1"), (c1, "2")], name="0")

a.add_probe_ext(*a.net_vertices(n_in)[1])     # 探针必须落在导线顶点
a.add_probe_ext(*a.net_vertices(n_out)[1])    # 序号自动唯一
a.save("out/ref/rc_lowpass.ms14")
```

一条命令生成 + 验证：

```bash
python tools/build_rc_lowpass.py                      # 1 kHz，出 out/ref/rc_lowpass.ms14
runtime\py32\python.exe tools/validate_rc.py out/ref/rc_lowpass.ms14 1000 main
```

**实测三点频响**（`tools/validate_rc.py` 用最小二乘拟合幅值和相位，
不是靠找峰）：

| 频率 | 实测增益 | 理论 \|H\| | 实测相位 | 理论 ∠H |
| --- | --- | --- | --- | --- |
| 100 Hz | 0.99520 | 0.99505 | −5.66° | −5.71° |
| 1 kHz（≈fc） | 0.70632 | 0.70745 | −45.06° | −44.97° |
| 10 kHz | 0.10015 | 0.09960 | −84.43° | −84.28° |

`fc = 1/(2πRC) = 1001 Hz`，`R1=1000 Ω`、`C1=159 nF` 均由 Multisim 自己报回
（`RLCValue`），不是我们写的值。

这是**一阶低通的教科书曲线**，也证明了输出不是静态假数据：如果电容没真正
参与，三点增益会是一条平线。

---

## 四、环境依赖

| 项 | 值 |
| --- | --- |
| Multisim | NI Circuit Design Suite **14.3**，装在 `C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3` |
| Python | 3.11+（编解码/XML 部分任意版本；COM 部分**必须 32 位**） |
| 第三方库 | **零**。编解码、XML、GUI 全是标准库 |
| 编译 DCL 工具（可选） | `gcc -O2 -o vendor/dcltool.exe vendor/dcltool.c vendor/blast.c` |
| 权限 | **不需要管理员**（前提：已关闭 `multisim.exe` 的"以管理员身份运行"兼容性设置，见下） |

### 关于那三个"访问数据库时发生错误"弹窗

本机打开 Multisim 会弹 3 个数据库错误框，是 **Win11 安全补丁导致的机器固有问题**，
与我们的代码无关（用户手动打开也有）。代码会自动点掉它们（`msui.dismiss_all()`）。

如果给 `multisim.exe` 设了"以管理员身份运行"，反而会弹出 UAC 对话框卡住自动化。
**建议关掉这个兼容性设置**——提权对生成电路文件没有任何帮助（我们直接写文件，不走元件库），
只会让每次启动都要人工批准。

---

## 五、30 秒上手（给接手的 agent）

```bash
cd multisim-ctrl

# 1. 解压语料库（108 个官方样例的明文 XML，ground truth）
mkdir -p /tmp/corpus && gunzip -k corpus/samples/PowerSupply.xml.gz -c > /tmp/corpus/PowerSupply.xml

# 2. 读一个样例，看结构
python - <<'PY'
import sys; sys.path.insert(0, "tools")
import msmodel, json
c = msmodel.Circuit.from_xml_file("/tmp/corpus/PowerSupply.xml")
print(json.dumps(c.summary(), ensure_ascii=False, indent=1))
PY

# 3. 生成验收电路并让 Multisim 打开
python tools/build_acceptance.py
python tools/verify_open.py out/ref/acceptance.ms14 out/verify.json
```

**先读 [docs/deadends.md](docs/deadends.md)，再读 [docs/next-steps.md](docs/next-steps.md)。**
这两份文档能避免重复踩坑。

---

## 六、文件导航

```
multisim-ctrl/
├── README.md                  ← 你在这里
├── docs/
│   ├── ms14-format.md         .ms14 格式规范（DCL 算法 + 容器 + 字节细节）
│   ├── circuit-xml.md         电路 XML 对象模型（坐标系/引脚/参数四处存储）
│   ├── probe.md               探针结构 + GUI 放置流程
│   ├── architecture.md        代码架构
│   ├── deadends.md            死路清单与避坑
│   ├── next-steps.md          路线图
│   ├── api.md                 COM API 全表（旧路线留存）
│   └── shots/                 关键截图（8 张，按时间顺序）
├── tools/
│   ├── dcl.py                 ★ DCL 编解码 + .ms14 读写（核心，零依赖）
│   ├── mssafe.py              ★★ XML 无损往返（属性值换行保护）——**所有读写必须走它**
│   ├── msmodel.py             ★ 电路对象模型层
│   ├── msbuild.py             ★ 装配器（克隆元件 + 连线 + 探针）
│   ├── build_rc_lowpass.py    ★ 用 add_part 生成 RC 低通（`--freq` 改频率）
│   ├── validate_rc.py         ★ RC 瞬态验证（最小二乘拟合幅值/相位 vs 理论）
│   ├── build_acceptance.py    ★ 验收电路生成脚本（`--divider` 出分压器版本）
│   ├── validate_acceptance.py ★ 验收仿真（读回电压 + 判定）
│   ├── test_mssafe.py         ★ 回归测试：XML 往返必须逐字节一致
│   ├── p18_run2.py            稳健的瞬态读取（**必须在 stop() 之前读**）
│   ├── index_samples.py       样例索引生成
│   ├── verify_open.py         启动 Multisim + 点弹窗 + 截图
│   ├── msui.py                GUI 高层封装（launch/click_img/shot）
│   ├── guiauto.py             Win32 GUI 原语（click/hotkey/foreground/screenshot）
│   ├── INDEX.md               ★ 160 个 p*_*.py 调查脚本的分阶段索引
│   └── ...                    其余为探索期一次性脚本，保留备查
├── vendor/
│   ├── blast.c / blast.h      Mark Adler 公版 PKWARE DCL 解压器（ground truth）
│   └── dcltool.c              C 版命令行编解码工具
├── corpus/
│   ├── samples/*.xml.gz       108 个官方样例解压后的明文 XML（gzip，共 7.4 MB）
│   ├── samples14/*.ms14       ★ 10 个原生 Multisim 14.3 电路（含 555 / 运放 / buck）
│   └── samples_index.json     每个样例的元件清单 (refdes, family, part)
├── out/ref/
│   ├── blank_circuit.xml      空白电路明文（148367 B，注入基底）
│   ├── own_blank.ms14         用自研压缩器重打包的空白电路（Multisim 能打开）
│   ├── acceptance.ms14        验收电路（V1 5V + R1 1kΩ + C1 + GND，探针在源网）
│   ├── acceptance_divider.ms14 验收电路（分压器，探针在中点，应读 2.5V）
│   ├── rc_lowpass.ms14        RC 低通（1kHz 激励，Vin/Vout 双探针）
│   ├── rc_lowpass_100Hz.ms14  RC 低通频响验证点（100 Hz）
│   ├── rc_lowpass_10kHz.ms14  RC 低通频响验证点（10 kHz）
│   ├── with_probes.ms14       Multisim 保存的、带探针的版本
│   └── probe_ext_full.xml     探针对象完整 XML（最重要的参考样本）
├── msc.py / cli.py / demo.py   COM API 路线（阶段一产物）
├── samples/                   原始 .ms12 示例电路
└── run.bat                    自带 32 位 Python + pywin32 的启动器
```

---

## 七、已验证 / 未验证（严格区分）

### ✅ 已在本机实测通过

- `.ms14` = PKWARE DCL (implode)，用 `blast.c` 交叉验证，解出长度与头部字段分毫不差
- 纯 Python 编解码往返一致
- **XML 无损往返**：`mssafe` 让 4 个原生样本往返后**逐字节一致**（`tools/test_mssafe.py`）
- 自研压缩器产出的 `.ms14` 能被 Multisim 正常打开（`own_blank.ms14`）
- 元件克隆（电气 + 绘图 + 引脚定义 + 模型）能正确渲染
- 导线生成（`CIITLinkComp`）能正确渲染
- 元件值四处同步修改后，界面显示正确更新（50Ω → 1kΩ）
- 免提权启动 Multisim、自动点掉 3 个数据库弹窗
- GUI 菜单导航放电压探针、保存后文件里确实出现探针对象
- **从空白电路生成分压器，中点实测 2.5 V**（证明 R1/R2 真的进了 SPICE 网表并导通）
- **从空白电路生成 V-R-C-GND 串联链，中点实测 5 V**（证明电容在直流下开路、电阻无压降）
- 原生 555 电路、运放电路经本仓库读写后，8 个输出读数与原文件完全一致
- **纯代码生成新式探针，且多探针可区分**：`LocalName` 序号唯一后
  `EnumOutputs()` 返回 `['V(探针1)', 'V(探针2)']`，两条读数各自正确
- **统一元件 API `add_part(family, part, ...)`**：不写死 XML ID，按家族/型号
  从真实 `.ms14` 解析模板；已覆盖 DC 源、正弦源、R、C、GND、探针
- **RC 低通三点频响全部对上理论**：100 Hz / 1 kHz / 10 kHz 的增益与相位
  误差分别 ≤ 0.0012 与 ≤ 0.15°（`tools/validate_rc.py`）

### ⬜ 未验证（接手后第一件事）

- `RESISTOR_RATED` / `CAPACITOR_RATED`（family `RATED_VIRTUAL`）路线
- 运放、555 等多引脚元件的通用 `add_part` 支持
- 元件符号库的位置（能否不靠克隆、直接按 (family, part) 新建元件）

### ❓ 已知未知

- `.ms14` 里 `&UNI..._uc<hash>` 的单位哈希表（电阻 `103a9`、电压 `100b5V` 是实测值，
  完整映射表未建）
- 探针序号超过 9 时的命名方式（当前只支持一位数字）

---

## 八、致谢与许可

- `vendor/blast.c` / `blast.h` 来自 zlib 仓库 `contrib/blast/`，作者 Mark Adler，
  公有领域。格式说明注释是本项目破解 `.ms14` 的钥匙。
- 官方样例电路来自 Multisim 安装目录
  `C:\Users\Public\Documents\National Instruments\Circuit Design Suite 14.3\samples\`。

本项目为私人研究用途，代码可自由使用。

## 2026-10-26 根因定论（取代 2026-10-24 的「克隆电阻开路」判断）

v0.1.0 里那句「克隆的 `RESISTOR_VIRTUAL` 在仿真中等效开路」是**症状描述，不是根因**。

真实根因：`CIITDiagram@SimState` 属性里是一段**多行**序列化文本

```
SimState="&ASCSIMULATION_INFO:list{ANALYSES:list{
ANALYSIS_LIST:list{}
ANALYSIS:list{
...
}}}"
```

XML 1.0 规范 3.3.3 规定属性值里的字面换行必须归一化成空格，`ElementTree`
严格遵守 → 这块数据被压平成一行 → Multisim 自己的解析器读不回来 → 仿真配置丢失。

所以不是「电阻克隆坏了」，而是**任何经过 ET 往返的文件都会坏**——包括原生文件。
分离实验（`out/p18_R_repack.ms14` vs `out/p18_S_etround.ms14`）：

| 版本 | 处理 | I(PR1) | 可读输出 |
| --- | --- | --- | --- |
| 原生 | — | 13.9977 A | 8/8 |
| R | 只重打包容器，XML 字节不动 | 13.9977 A | 8/8 |
| S | 仅 ET 解析+序列化 | 0 A | 3/8 |

修复后同一个分压器：中点 **2.5 V**（期望 2.5），极差 1.3e-15。

**教训：凡是要动 `.ms14` 的代码，XML 读写必须走 `mssafe`，不能用裸 `ET.fromstring`
/ `ET.tostring`。** 回归测试 `tools/test_mssafe.py` 守住这条。
