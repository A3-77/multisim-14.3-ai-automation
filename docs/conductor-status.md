# 接管状态（Conductor 视角）

> 更新时间：2026-10-24 13:15
> 执行体：WorkBuddy AI（本机 GUI 会话，通过 codebuddy gateway 驱动）
> 指挥：DSH agent（本文件由指挥方维护，WorkBuddy 每轮任务从这里取上下文）

---

## 一、分工

- **指挥方**：拆任务、定验收标准、跑关键判定实验、验收产物、维护本文件。
- **WorkBuddy**：写代码、跑 COM/GUI、做重复实验与批量验证（它是免费的算力）。
- **不要**让 WorkBuddy 写"总结/推送 GitHub"，也不要让它重新研究已解决的问题。

## 二、已验证事实（2026-10-24 12:35–13:10 实测）

### 1. WorkBuddy 控制通道

- 网关：`http://127.0.0.1:<port>`，本机当前 **59689**（不是文档里的 49294）。
- 驱动：`C:\Users\A377\xs0image\workbuddy-control-skill\scripts\wb.ps1`
  - `wb.ps1 status -Port 59689` → `{"status":"ok"}`
  - `wb.ps1 run "<prompt>" -Port 59689 -TimeoutSec 2400`
- 长任务用后台 job 跑；流断了用 transcript 兜底（driver 自带）。
- **坑**：`powershell.exe`（5.1）读不了 UTF-8 中文脚本，必须用 `pwsh`（7.x）。

### 2. Multisim COM

- 32 位 Python：`runtime\py32\python.exe`（带 pywin32）。
- COM 不稳：一次分析失败后可能 segfault / 再连报「拒绝访问」。
  **对策**：每个文件单独一个进程；跑前 `taskkill /F /IM multisim.exe`；失败后等几秒再试。
- `samples/7812.ms12` 是可靠的"能跑"基准：`EnumOutputs()` 返回 `V(Probe1), I(Probe1)`，`dc_op()` 有数。

### 3. 探针（本项目真正的卡点）

| 类型 | 类 | 绑定方式 | COM 能取数？ |
| --- | --- | --- | --- |
| 新式 | `CiProbeExtComp` + `CIITProbeExtComponent` | **几何吸附**：Transformer 位置必须落在导线上 | 枚举得到，但 `GetOutputData` 报「输出未找到」 |
| 老式 | `CiProbeComp` + `CIITProbeComponent` | 绘图对象上**显式 `NetName`**（如 `&ASC4`），并在 `CiCircuit/Probes` 注册 | ✅ 能，且一个探针同时给 V 和 I |

实测证据：
- 把 with_probes.ms14 的探针从 (558,333)（悬空）移到 (400,300)（net1 导线上）
  → `EnumOutputs()` 从 0 个变成 `V(探针1)`。**绑定 = 位置。**
- 但新式探针取不到数据（DC/瞬态都失败）。改名成 ASCII `Probe1` 也一样。
- 老式探针（7812.ms12）在 COM 里工作正常。

**结论：生成电路时应生成老式 `CIITProbeComponent` 探针，而不是新式 ProbeExt。**

### 4. acceptance 电路本身

- `out/ref/acceptance.ms14`：V1(5V) + R1(1kΩ) + GND，三条导线，界面渲染完整
  （截图 `out/shots/gui_after_run.png`）。
- V1 的 2 脚确实在 net0（`CiNode/Ports` 里），电路电气上是闭合的。

## 三、任务队列

| 优先级 | 任务 | 验收 | 状态 |
| --- | --- | --- | --- |
| P0 | 自建电路跑仿真，证明 5V/1kΩ → 5mA | 探针读数 5V + RLCValue 1000Ω + 网表/CSV | ⏳ 被探针卡住 |
| P1 | 老式探针纯代码生成 | 克隆后 COM 读出 5V | 🔄 进行中 |
| P0' | 探针搞定后重跑验收，落盘 JSON/CSV | `out/p0_validation.json`、`out/p0_waveform.csv` | 待做 |
| P2 | 统一元件 API（family/part → 模板） | `add("RESISTOR","R",...)` 一套接口 | 待做 |
| P3 | Circuit IR + 自然语言→电路 | 一句话生成 `.ms14` 且能仿真 | 待做 |
| P4 | 自动布局/自动连线 | 生成图不重叠、不交叉、可读 | 待做 |

## 四、关键文件

```
multisim-ctrl/
  out/ref/acceptance.ms14        自建电路（无探针）
  out/ref/with_probes.ms14       GUI 放过新式探针的版本（探针悬空）
  out/donor_spice.ms14           样例重打包，COM 可正常仿真
  samples/7812.ms12              老式探针 + COM 可读数 的黄金样本
  tools/msbuild.py               元件克隆/连线（探针要加到这里）
  tools/build_acceptance.py      验收电路生成脚本
```

指挥方的实验脚本（不在仓库里）：`C:\Users\A377\Ni\analysis\*.py`
