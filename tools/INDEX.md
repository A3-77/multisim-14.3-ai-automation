# tools/ 索引

这个目录里 `p*_*.py` 是**调查期的一次性脚本**，不是产品代码。
它们的作用是「证据」——每一条结论都能被重跑验证。别删。

## 先看这几个（产品代码 / 长期维护）

| 文件 | 作用 |
|---|---|
| `dcl.py` | PKWARE DCL 编解码 + `.ms14` 容器读写。零第三方依赖 |
| `mssafe.py` | **XML 无损往返**。保护属性值里的 `\r\n\t`，绕开 XML §3.3.3 归一化 |
| `msmodel.py` | 电路对象模型层（`Circuit` / 元件 / 引脚 / 网表） |
| `msbuild.py` | 装配器（从语料库克隆元件 + 连线 + 放探针） |
| `build_acceptance.py` | 验收电路生成（默认源网探针；`--divider` 出分压器版） |
| `validate_acceptance.py` | 验收仿真 + 判定（读回电压/电流，比对期望值） |
| `test_mssafe.py` | 回归测试：4 个原生样本 XML 往返必须逐字节一致 |
| `p18_run2.py` | 稳健的瞬态读取模板（**必须在 `stop()` 之前 `read()`**） |

## 调查阶段对照表

| 阶段 | 脚本前缀 | 在查什么 | 结论落点 |
|---|---|---|---|
| 1–9 | `p1_*` `p2_*` `p6_*`–`p9_*` | `.ms12` 早期格式、7812 电源电路、探针克隆、基底裁剪 | `docs/ms14-format.md` |
| 11–13 | `p11_*`–`p13_*` | COM 接口探测、静态 XML 逐节点比对、RC 低通 | `docs/api.md`、`docs/deadends.md` |
| 14–16 | `p14_*`–`p16_*` | 波形读取时序、`V(pin)` 注入、符号属性/引脚类型比对 | `docs/probe.md` |
| 17 | `p17_*` | 探针与引脚普查：`NodeText`、junction、`PortID`、`ConnectList` | `docs/deadends.md` 三～五 |
| 18 | `p18_*` | **根因定位**：分离容器压缩 vs XML 往返，最终锁定 `CIITDiagram@SimState` | `docs/p0-acceptance.md`、`docs/deadends.md` 六 |

### p18 里最关键的四支（想复现根因就看它们）

1. `p18_ladder.py` —— L1 控制实验。**原生文件原样过一遍保存路径**，电压还对但电流归零 ⇒ 写盘路径本身有损。
2. `p18_repack.py` —— 分离两个变量。只重打包容器（XML 字节不动）完好；裸 `ET` 往返就废。**这张表是判决书**。
3. `p18_xmldiff.py` —— 定位损坏点。行数 18769 → 11294，首个分叉正好在 `SimState="..."`。
4. `p18_divdc.py` / `p18_matrix.py` —— 修复后的阳性验证。纯电阻分压中点读 2.5 V。

## 一次性脚本的用法

基本都是「打开某个 `.ms14` → dump 某一类对象 → 打印」。改脚本顶部的路径常量再跑即可。
输出一般落在 `out/`（已被 gitignore，只有 `out/ref/` 入库）。

## 注意

- 跑任何 COM 脚本前先 `taskkill /F /IM multisim.exe`，残留进程会导致读到空数据。
- 一个进程只开一个 `.ms14`。
- 任何改动 `.ms14` 的代码，XML 读写必须走 `mssafe`，不要用裸 `ET.fromstring` / `ET.tostring`。
