# 原生 .ms14 样本（10 个）

## 用途

这 10 个文件是**原生 Multisim 14.3 保存的电路**，是格式逆向的 ground truth。
主要用途有三个：

1. `tools/test_mssafe.py` 拿它们做 XML 无损往回的回归测试（必须逐字节一致）。
2. `tools/msbuild.py` 从它们身上**克隆元件**（电阻、电容、电源、地、探针的完整对象图）。
3. 调查期用来对比「原生 vs 生成」的静态差异。

## 来源

来自公开流传的 Multisim 教学仿真实例合集，供格式研究使用。
文件名保持原样，便于对照原始资料。

| 文件 | 用到的特征 |
|---|---|
| `Amplificador para resistencia de 1mOhm.ms14` | 3 个 GROUND、3 个 `RESISTOR_VIRTUAL`、2 个 `DC_POWER` —— 克隆基底 |
| `buck.ms14` | 90 根导线、44 个 junction、27 个 `CSCH_CAPVirtualComponentPin` —— 结构最全 |
| `nivel de agua con 555.ms14` | 555 定时器 + 双电源，行数最多（26140 行） |
| `05 滤波器.ms14` | `RESISTOR_RATED` / `CAPACITOR_RATED`（family `RATED_VIRTUAL`） |
| `02 同相加法器.ms14` | 运放 + `RATED_VIRTUAL` 系列 |
| `04 仪表放大器.ms14` | 运放，多级 |
| `01 3D元件仿真.ms14` | 3D 元件 |
| `03 门电路基本用法.ms14` | 数字门 |
| `De cuadrada a sin.ms14` | 波形变换 |
| `Fuente capacitiva final.ms14` | 电容降压电源 |

## 注意

- 这些文件**不要用裸 `xml.etree` 处理**。它们的 `CIITDiagram@SimState` 属性里存着多行仿真状态，
  一旦经过 `ET.fromstring` + `ET.tostring` 就会永久损坏（详见 `docs/deadends.md` 第六节）。
  读改写一律走 `tools/mssafe.py`。
- 如果仓库要缩减体积，可以只保留前 4 个——`test_mssafe.py` 用的就是那 4 个。
