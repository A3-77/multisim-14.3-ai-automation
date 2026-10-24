# 给接手者的路线图

> 按优先级排序。每一项都写了**为什么是这个优先级**、**具体做什么**、**怎么算完成**。
> 建议从上往下做，不要跳。

---

## P0 —— 跑一次仿真，确认 1kΩ 真的生效（预计最快）

### 为什么优先

现在"R1 = 1kΩ"只是**界面显示正确**，没有证据表明仿真引擎读到的也是 1kΩ。
如果底层数值没生效，那前面的工作有重大隐患，必须先排除。

### 做什么

用 COM API 在 `out/ref/acceptance.ms14` 上跑一个直流工作点分析或瞬态分析。

**前置问题**：这个电路**没有探针**，而 COM API 的 `EnumOutputs()` 只枚举探针。
所以要么：

- **方案 A（推荐，最快）**：先用 GUI 放一个探针（流程见 `docs/probe.md` 第 3 节，
  `out/ref/with_probes.ms14` 里已经有 2 个探针了，可以直接用它），
  然后用 COM 跑仿真读数。
- 方案 B：用 SPICE 网表绕开（如果有导出网表的功能）。

### 怎么算完成

R1 的电流 = **5 mA**（5V / 1kΩ）。或者电阻两端电压 = **5V**。

如果是 5V / 50Ω = 100 mA，说明值没真正生效，回到
[circuit-xml.md 第 4 节](../docs/circuit-xml.md) 继续查。

### 代码入口

```python
# 必须 32 位 Python
import sys; sys.path.insert(0, ".")
import msc
app = msc.connect()
c = app.OpenCircuit(r"...\with_probes.ms14")
# 参考 msc.py / demo.py 里的 SetOutputRequest / RunSimulation / GetOutputData
```

`demo.py` 里有完整可用的取数流程（扫参与时域两个例子）。

---

## P1 —— 搞清探针怎么绑定网络（本项目最大未解之谜）

### 为什么优先

这是验收标准里明确要求的（"在电阻两端放电压探针并保存"），
也是 P0 的前置（没探针取不到数）。

### 已知事实（详见 [probe.md 第 4 节](probe.md)）

- `CiProbeExtComp/Ports` 是空的
- 探针绘图对象里没有任何 `Connect`/`Node`/`NetName`
- 探针 CiID 只出现 3 次，都不引用网络
- 必须在 `CiCircuit/ProbeExts` 里注册

### 具体做什么

**第一步：逐元素 diff。**
对比放探针前的 `out/ref/acceptance.ms14` 和放探针后的 `out/ref/with_probes.ms14`，
列出**所有**新增/变化的元素（不只是按 Class 计数）。

```python
import sys; sys.path.insert(0, "tools")
import dcl, xml.etree.ElementTree as ET

a, _ = dcl.read_ms14("out/ref/acceptance.ms14")
b, _ = dcl.read_ms14("out/ref/with_probes.ms14")
ta, tb = ET.fromstring(a), ET.fromstring(b)

def keys(t):
    """每个元素的 (tag, 关键属性) 作为指纹"""
    out = {}
    for e in t.iter():
        k = (e.tag, e.get("CiID") or e.get("ID") or e.get("Class") or "")
        out.setdefault(k, []).append(ET.tostring(e, encoding="unicode"))
    return out

ka, kb = keys(ta), keys(tb)
for k in sorted(set(ka) | set(kb)):
    va, vb = ka.get(k, []), kb.get(k, [])
    if len(va) != len(vb):
        print("数量变化", k, len(va), "->", len(vb))
    elif va != vb:
        print("内容变化", k)
```

**第二步：重点查那 5 个新增的 `CIITPinConnectorComp` 和 6 条新增的 `CIITLinkComp`。**
它们在哪个父对象下？`ConnectList` 指向什么？这很可能就是探针的网络连接点。

**第三步：如果没找到显式引用，验证"几何推断"假设。**
改 `with_probes.ms14` 里探针的 `Transformer-M20/M21` 到另一个位置，
保存，用 Multisim 打开，看它连到哪个网络，再保存，diff。

### 怎么算完成

能说清楚"探针通过什么机制绑定到网络"，并能用纯代码生成一个绑定到指定网络的探针。

---

## P2 —— 纯代码生成探针

### 做什么

照抄 `out/ref/probe_ext_full.xml`（完整参考样本），用 `copy.deepcopy` 克隆，
改这些字段：

| 字段 | 改成 |
| --- | --- |
| `Transformer-M20/M21`（绘图对象） | 目标位置 |
| `CiProbeExtComp`（绘图对象） | 新电气对象 CiID |
| `NI_EWB_COMPHANDLE_EXT/Data` | 新绘图对象 ID |
| `SymCompID`（电气对象） | 新绘图对象 ID |
| `InstanceID` | 新 GUID |
| `LocalName` / `InfoBoxText` | 探针名 / 信息框文字 |
| `CiCircuit/ProbeExts` | 追加 `<Item CiID="新CiID"/>` |

然后按 P1 的结论补上网络绑定。

### 怎么算完成

```python
python tools/build_acceptance.py     # 生成带探针的电路
python tools/verify_open.py out/ref/acceptance.ms14 out/verify.json
```

截图里能看到探针，且 `CiProbeExtComp` 数量正确。

---

## P3 —— 把"自然语言 → 电路"的接口做出来

### 为什么

用户最终要的是这个。前面都是铺路。

### 做什么

写一个 `create_circuit(description: str) -> path` 函数，至少支持：

```
"新建一个 5V 直流电源串联 1kΩ 电阻接地的电路，在电阻两端放电压探针并保存。"
```

拆解：
1. **解析**：提取元件清单（类型、值、位号）+ 拓扑（串联/并联）+ 附加要求（探针）。
   - 简单做法：正则 + 关键词表。
   - 稳妥做法：让 LLM 输出结构化 JSON，代码只做装配。
2. **查元件模板**：从 `corpus/samples_index.json` 找 (family, part) 匹配的样例，
   用 `msbuild.Donor` 抽模板。目前可用的：
   - `("POWER_SOURCES", "DC_POWER")` → `SPICE Command Line.ms14` 的 `V2`
   - `("RESISTOR", "RESISTOR_VIRTUAL")` → `SPICE Command Line.ms14` 的 `R1`
   - `("POWER_SOURCES", "GROUND")` → 同上
3. **布局**：简单的栅格布局（按拓扑分层，每层 y 固定，x 递增）。
4. **连线**：`Assembler.connect()`。
5. **放探针**：P2 的成果。
6. **保存 + 验证**：`verify_open.py` 打开截图。

### 怎么算完成

输入那句话，输出一个 `.ms14`，Multisim 打开后是正确的电路，仿真读数正确。

---

## P4 —— 扩展元件库（长期）

### 问题

现在靠"从样例克隆元件"，只能覆盖样例里出现过的 (family, part)。
`corpus/samples_index.json` 里有 108 个样例的元件清单，可以看看覆盖度。

### 方向

1. **从 Multisim 元件库直接取符号**。元件库位置还没找到——
   查过 `database/`、`ProgramData`、安装目录下的 `.usr`/`.prz`/`.mdb` 文件，没定位到。
   **这是有价值但没做的调研**。
2. **攒自己的元件模板库**：每用到一种新元件，就把它的对象子树存成模板 JSON/XML，
   建一个 `templates/` 目录。这是最稳的渐进方案。
3. **单位哈希表**：`&UNI<值>_uc<hash>` 的 hash 算法未知，
   现在靠"继承旧值的后缀"绕过。可以统计更多样例建一张查找表。

---

## 附：一句话状态总结

```
✅ .ms14 编解码（纯 Python，零依赖）
✅ 从空白电路生成 V1(5V) + R1(1kΩ) + GND + 3 导线，Multisim 正常打开渲染
✅ 元件值五处同步，界面显示正确
✅ GUI 放电压探针并保存（探针对象确实落盘）
✅ 免提权启动 Multisim + 自动点弹窗 + 截图
⬜ 仿真验证（代码就绪，未跑）
⬜ 探针纯代码生成（结构已摸清，网络绑定机制未明）
⬜ 自然语言 → 电路 接口
```
