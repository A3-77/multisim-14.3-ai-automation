# P0 验收 —— 从空白 .ms14 生成可仿真的真实电路

> 日期：2026-10-24 首版；**2026-10-26 v0.2.0 根因更正**
> 环境：Multisim 14.3（本机）、32 位 Python 3.11（`runtime/py32`）、COM `MultisimInterface.MultisimApp`

## 结论（v0.2.0，已复核）

从空白电路出发，用纯代码生成，Multisim 能打开并**真实仿真**：

| 用例 | 拓扑 | 探针位置 | 期望 | 实测 | 结论 |
| --- | --- | --- | --- | --- | --- |
| `acceptance.ms14` | V1(5V) + R1(1k) + C1(1pF) + GND | 源网（net1） | 5.0 V | **5.0 V**，极差 1.8e-15 | ✅ |
| `acceptance_divider.ms14` | V1(5V) + R1(1k) + R2(1k) + C1(1pF) + GND×2 | **分压中点** | 2.5 V | **2.5 V**，极差 1.3e-15 | ✅ |

两次都是 2000 个采样点、`EnumOutputs` 非空、`RLCValue('R1') = 1000.0 Ω`。

**为什么两个用例都要：** 探针落在源网只能证明电源在（`acceptance.ms14` 的 5.0 V
即使电阻开路也成立）。**中点读到 2.5 V 才是电阻真的进了 SPICE 网表并导通的证据。**

复现：

```bash
cd multisim-ctrl
runtime\py32\python.exe tools\build_acceptance.py              # -> out/ref/acceptance.ms14
runtime\py32\python.exe tools\build_acceptance.py --divider     # -> out/ref/acceptance_divider.ms14
runtime\py32\python.exe tools\validate_acceptance.py out/ref/acceptance.ms14 source 5.0
runtime\py32\python.exe tools\validate_acceptance.py out/ref/acceptance_divider.ms14 divider 2.5
runtime\py32\python.exe tools\test_mssafe.py                    # 回归：XML 往返逐字节一致
```

## 真正的根因（2026-10-26）

**`CIITDiagram@SimState` 属性里是一段多行序列化文本，被 XML 属性值归一化压平了。**

Multisim 把整个仿真配置序列化进 `SimState` 属性，原始 XML 里是**真的换行**：

```
<CIITDiagram Class="CIITDiagram" ... SimState="&ASCSIMULATION_INFO:list{ANALYSES:list{
ANALYSIS_LIST:list{}
ANALYSIS:list{
...
}}}"/>
```

XML 1.0 规范 3.3.3 要求解析器把属性值里的字面 `\r` `\n` `\t` 一律替换成空格。
`xml.etree.ElementTree` 严格遵守 → 多行数据被压平成一行 → Multisim 自己的解析器
读不回来 → 仿真配置丢失 → **只剩电源在动，R/C 全部开路**。

### 三行分离证据

同一份原生文件 `Amplificador para resistencia de 1mOhm.ms14`，逻辑零改动：

| 版本 | 处理 | V(PR1) | I(PR1) | 可读输出 |
| --- | --- | --- | --- | --- |
| 原生 | — | 84 V | **13.9977 A** | 8/8 |
| `p18_R_repack.ms14` | 只重打包容器，XML 字节不动 | 84 V | **13.9977 A** | 8/8 |
| `p18_S_etround.ms14` | 仅 ET 解析 + 序列化 | 84 V | **0 A** | 3/8 |

电压还在、电流归零、部分输出读不出来——**这就是长期被误判成「克隆的电阻是开路的」
那个现象**，其实跟克隆无关，任何经过 ET 往返的文件都会坏，原生文件也一样。

### 修复

新增 `tools/mssafe.py`：解析前把属性值内部的 `\r\n\t` 换成 ASCII 占位符
（`@@WB_NL@@` 等），序列化后还原，并补回原始声明与文件末尾换行。
`msmodel.Circuit` 的 `load` / `save` / `from_xml_file` 全部改走它。

```python
# 正确
self.tree = mssafe.parse(xml_bytes)          # 读
xml = mssafe.serialize(self.tree)            # 写

# 错误 —— 会静默毁掉仿真配置
self.tree = ET.fromstring(xml_bytes)
xml = ET.tostring(self.tree, encoding="ascii", xml_declaration=True)
```

回归测试 `tools/test_mssafe.py`：4 个原生样本（运放 / buck / 555 / 滤波器）
往返后**逐字节一致**（仅归一化「声明」与「`<Item />` 的自闭合空格」两处无害差异）。

## 被证伪的假设（别再走一遍）

这一轮之前，有大量精力花在「找缺失的结构」上，全部落空：

| 假设 | 检验方式 | 结果 |
| --- | --- | --- |
| 导线缺 `NodeText` / `CODNodeTextComp` 网络分组对象 | 补齐后重测 | 不是原因 |
| 3 引脚网缺 `CODPinComp` 交汇结点（junction） | 搭纯电阻分压器（全 2 引脚网）+ 3 引脚中点分压器 | **都不需要**，中点 2.5 V |
| 缺 `CSCH_CAPVirtualComponentPin@lastnet` 引脚网络缓存 | 统计 + 注入 | 不是原因（缓存而已） |
| `CIITPinSymbolComp@PortID` 指向同一个端口 | 逐元件核对 | 全部正确，无重复 |
| 虚拟元件缺 `Model` 属性 | 与原生对比 | 原生虚拟 R 也没有 |
| `doubles` 有值 vs 原生为空 | 清空后重测 | 不是原因 |
| 供体文件损坏 | 换 10 个原生案例库文件当供体 | 不是原因 |
| 探针绑错网络 | 造「node2 由独立 3V 源硬定」的电路 | 探针**精确读到 3 V**，绑定正确 |

## 仍然成立的规律（后续会用到）

1. **必须在 `stop()` 之前读数据** —— 部分电路 stop 后 `GetOutputData` 报「未指定的错误」。
   用 `tools/p18_run2.py` 的写法（run → wait → read → stop）。
2. **纯直流电路（只有 R + 源）不会进入 running** —— 没有可积分过程，属正常；
   要取数要么用 DC 工作点（`dc_op`，本仓库实测可用），要么加一个极小电容走瞬态。
3. **探针位置必须精确落在导线顶点**（不是线段中间、不是引脚端点），否则不注册成 output。
4. **一个文件里放两个 ProbeExt 会拿到同名输出**（都叫 `V(探针2)`），COM 读取直接报错。
   要么一个文件一个探针，要么给探针显式命名（未实现）。
5. COM 不稳定：一次分析失败后可能 segfault；**一个文件一个进程**、跑前 `taskkill /F /IM multisim.exe`。

## 产物

| 文件 | 说明 |
| --- | --- |
| `out/ref/acceptance.ms14` | 验收电路（源网 5.0 V） |
| `out/ref/acceptance_divider.ms14` | 验收电路（分压中点 2.5 V） |
| `out/p0_validation.json` | 两次运行的完整记录（outputs / RLC / V 统计 / 判定 / 时间戳） |
| `out/p0_waveform_source.csv` | 2000 点波形，恒 5.0 V |
| `out/p0_waveform_divider.csv` | 2000 点波形，恒 2.5 V |

## 下一步

- P1：统一 `add_part(family, part, ...)`，作为 Circuit IR 的底座；
- P1.5：RC 低通滤波器（多节点 + 真实瞬态波形，不只是恒压）；
- P2：108 个样例 + 10 个原生 14.3 案例的元件覆盖率；
- P3：Circuit IR + 自然语言 → 电路。
