# 电路 XML 对象模型

> 解密 `.ms14` 得到的是 XML。这份文档讲 XML 内部怎么组织。
> 配套实现：`tools/msmodel.py`（读/查/改）、`tools/msbuild.py`（克隆/装配）。

---

## 1. 两棵平行树

根是 `CIITDiagram`，下面挂着**两棵互不相交、靠 CiID 关联**的树：

```
CIITDiagram
├── Elements                       ← 电气树（仿真用）
│   └── Item[CiID=..., Class=...]
│       ├── CiComponent   元件     CiComponent@LocalName = 位号
│       ├── CiPort        引脚     CiPort@Component = 属于哪个元件
│       ├── CiNode        网络     CiNode/Ports/Item@CiID = 连了哪些引脚
│       ├── CiModel       模型
│       ├── CiProbeComp / CiProbeExtComp   探针
│       └── CiCircuit     电路根   （用 CiID 索引 Models/Nodes/Probes/Components）
└── Components
    └── CODComposite
        ├── Objects                ← 绘图树（界面用）
        │   └── Item[ID=..., Class=...]
        │       ├── CIITSymbolComp        元件符号（内含若干子对象）
        │       ├── CIITLinkComp          导线
        │       ├── CIITProbeExtComponent 探针
        │       ├── CIITSymTextCompName   位号文字
        │       ├── CIITSymTextCompValue  值文字
        │       ├── CIITPinSymbolComp     引脚符号
        │       └── CIITPinConnectorComp  引脚连接点
        └── ReferencedComponents   ← 引脚定义
            └── Item[ID=...] / CODPinComp   （带 CenterX/CenterY 绝对坐标）
```

**关键理解**：改一个元件要同时改两棵树。只改电气树，界面不变；只改绘图树，仿真不变。

`CiCircuit` 是索引中心，结构大致：

```xml
<CiCircuit Class="CiCircuit" LocalName="&ASC..." ...>
  <Models>      <Item CiID="..." /> ... </Models>
  <Nodes>       <Item CiID="..." /> ... </Nodes>
  <Probes>      <Item CiID="..." /> ... </Probes>
  <Components>  <Item CiID="..." /> ... </Components>
</CiCircuit>
```

**新加的元件/节点必须往这些列表里追加 `Item`，否则 Multisim 不认。**

---

## 2. 坐标系与变换

### 2.1 元件位置

元件位置 = **绘图子对象上的 `Transformer-M20` / `Transformer-M21`**。
旋转/镜像在 `Transformer-M00/M01/M10/M11`（单位矩阵 = 未旋转）。

```xml
<CIITSymbolComp ... Transformer-M00="1." Transformer-M01="0."
                     Transformer-M10="0." Transformer-M11="1."
                     Transformer-M20="360." Transformer-M21="300." />
```

单位与符号局部坐标一致（元件宽约 27 单位），**栅格通常是 9**。

一个元件符号里可能有多个子对象带 `Transformer-*`，平移时要**全部**平移：

```python
for el in item.iter():
    if el.get("Transformer-M20") is not None:
        el.set("Transformer-M20", "%g." % (float(el.get("Transformer-M20")) + dx))
        el.set("Transformer-M21", "%g." % (float(el.get("Transformer-M21")) + dy))
```

### 2.2 引脚绝对坐标（重要公式）

**引脚绝对坐标 = 引脚符号变换矩阵 × 局部连接点**

```python
x = M00 * ptCenterX + M10 * ptCenterY + M20
y = M01 * ptCenterX + M11 * ptCenterY + M21
```

其中 `ptCenterX/ptCenterY` 来自 `CIITPinConnectorComp`，
`M00..M21` 来自外层的 `CIITPinSymbolComp`。

**实测 20/20 与 `ReferencedComponents` 里 `CODPinComp` 的 `CenterX/CenterY` 完全匹配。**

### 2.3 引脚引用链

```
CIITPinSymbolComp@PortID          → CiPort（电气树的引脚）
CIITPinSymbolComp/PinName         → 引脚名（如 "1"、"2"）
CIITPinSymbolComp/CIITPinConnectorComp
    ├── ptCenterX / ptCenterY     → 局部连接点
    └── ConnectList/Item@ID       → ReferencedComponents 里的 CODPinComp 定义
```

`CODPinComp` 定义带**绝对坐标**，是导线端点定位的唯一依据。
所以克隆元件时必须把引脚定义也复制一份并平移：

```python
new_def = copy.deepcopy(src)
new_def.set("ID", new_id)
list(new_def)[0].set("CenterX", "%g" % (float(old_cx) + dx))
list(new_def)[0].set("CenterY", "%g" % (float(old_cy) + dy))
```

---

## 3. 元件身份

`CiComponent/Attributes` 是一个 `Item` 列表，每个槽位有特定含义：

| 槽位 | 内容 | 说明 |
| --- | --- | --- |
| `[2]` | `CiaParamList` | 参数值，见下 |
| `[4]` | `CiaCollString` | **元件身份**：前两项 = `(family, part)` |

身份示例（实测）：

| family | part | 说明 |
| --- | --- | --- |
| `RESISTOR` | `RESISTOR_VIRTUAL` | 虚拟电阻 |
| `POWER_SOURCES` | `DC_POWER` | 直流电压源 |
| `POWER_SOURCES` | `GROUND` | 接地 |

```python
def ident(comp):
    for cs in comp.find("Attributes")[4].iter("CiaCollString"):
        vals = [i.get("Value").replace("&ASC", "") for i in cs.iter("Item")]
        vals = [v for v in vals if v.strip()]
        if vals:
            return vals[0], (vals[1] if len(vals) > 1 else "")
```

> `&ASC` 前缀是 Multisim 的本地化字符串标记，属性值里转义成 `&amp;ASC`。
> 读的时候统一 `.replace("&ASC", "")`。

---

## 4. 元件值存在四处（最容易踩的坑）

Multisim 把同一个参数值存了**四份**，只改一份界面不会更新：

| # | 位置 | 内容 | 示例 |
| --- | --- | --- | --- |
| 1 | `Attributes[2]/CiaParamList/doubles[1]` | 数值 | `"1000."` |
| 2 | `Attributes[2]/CiaParamList/parameters[1]` | 人类可读 | `"&ASC1k"` |
| 3 | `Attributes[41]/CiaCString@String` | **权威副本** | `"&ASC1k"` |
| 4 | `Attributes[42]/CiaCString@String` | 显示缓存 | `"&UNI1k_uc103a9"` |
| 5 | 绘图对象 `CIITSymTextCompValue@Output` | 图上渲染文字 | `"&UNI1k_uc103a9"` |

`CiaParamList` 里还有第三组平行数组 `strings`（`&ASCParam` 这种类型标记），不用改。

**踩坑记录**：最初只改了 #1 和 #5，Multisim 界面仍显示 `50Ω`。
放大截图逐像素确认后，才定位到 #2/#3/#4 也要改。
改完全部五处，界面立刻变成 `1kΩ`。

> **注意**：槽位号 41/42 不是所有元件都有。部分元件 `Attributes` 不足 43 项，
> 直接索引会 `IndexError`。必须先判断 `len(items) > 42`。

封装好的方法（`msmodel.Circuit.set_value`）：

```python
c.set_value_by_refdes("R1", 1000.0)     # 内部自动同步全部五处
```

### 数值格式约定

- 数值槽：`"1000."` —— 带尾点的十进制（`_num_str()` 保证）。
- 人类可读：工程记数法，`1000 → "1k"`、`0.0005 → "500u"`、`47000 → "47k"`。
  尾数落在 `[1, 1000)`，最多 4 位有效数字，去掉多余的 0。
  规则来自 108 个官方样例的 76 组（数值, 显示）配对统计。
- 显示缓存：`&UNI<人类可读>_uc<单位哈希>`。**单位哈希从同类元件的旧值里继承**
  （`old.split("_uc", 1)[1]`），因为哈希算法未知。

---

## 5. 网络与导线

### 5.1 网络（CiNode）

```xml
<Item CiID="123" Class="CiNode">
  <CiNode Class="CiNode" LocalName="&ASC1" Circuit="<电路CiID>">
    <Attributes />
    <Ports>
      <Item CiID="<引脚CiID>" />
      ...
    </Ports>
  </CiNode>
</Item>
```

同时，每个 `CiPort` 的 `Nodes/Item` 里也要回指这个网络（**双向引用**）：

```xml
<CiPort ...>
  <Nodes><Item CiID="<网络CiID>" /></Nodes>
</CiPort>
```

只建单向引用会导致 Multisim 里导线连不上。

### 5.2 导线（CIITLinkComp）

```xml
<Item ID="456" Class="CIITLinkComp">
  <CIITLinkComp Class="CIITLinkComp"
      instID="0" Stretchable="1" Moveable="1" ...
      Connect1="<引脚定义ID>"      <!-- ReferencedComponents 里的 CODPinComp ID -->
      Connect2="<引脚定义ID>"
      Node="<网络CiID>"
      Layer="511" PenColor="0" ...
      Transformer-M00="1." Transformer-M01="0."
      Transformer-M10="0." Transformer-M11="1."
      Transformer-M20="0." Transformer-M21="0."
      Hidden="0" ShowWhenNetSet="0">
    <Points>
      <Item X="360" Y="300" />
      <Item X="520" Y="300" />
    </Points>
    <ElectricalObject HiddenName="0">
      <ModifierInfo>
        <Element NetModifier="&ASCNI_EWB_NET_AUTONAMED">
          <Item Value="" Guid="{...}" />
        </Element>
      </ModifierInfo>
    </ElectricalObject>
  </CIITLinkComp>
</Item>
```

- `Connect1/Connect2` = 引脚**定义** ID（不是引脚 CiID，也不是元件 CiID）。
- `Node` = 网络 CiID。
- `Points` 是折线顶点，**相对** `Transformer-M20/M21`（导线通常为 0，所以等价绝对坐标）。
- 两点不在同一水平/竖直线上时，用 L 形折线（先横后竖）连接。

---

## 6. ID 分配规则

`CiID` / `ID` 都是十进制字符串。实测 Multisim 分配的是**8 的倍数**：

```python
def new_id(self):
    self._next += 8
    while self._next in self.used:
        self._next += 8
    self.used.add(self._next)
    return str(self._next)
```

初始值 = `max(已用 ID) + 8`。克隆时**必须**换新 ID，否则会和原元件冲突。

`InstanceID` 是 GUID，格式 `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`，大写，
克隆时用 `uuid.uuid4()` 生成新的。

---

## 7. 位号与显示文字

```python
def set_refdes(self, ciid, refdes):
    c.set("LocalName", "&ASC" + refdes)              # 电气树
    for el in symbol.iter():
        if el.tag == "CIITSymbolComp":
            el.set("InstanceRefDes", "&ASC" + refdes)   # 绘图树
        elif el.tag == "CIITSymTextCompName":
            el.set("Output", "&ASC" + refdes)           # 图上文字
```

`CIITSymTextCompValue@Output` 同理，存的是值文字（`&UNI1k_uc103a9`）。

---

## 8. 空白基底

`out/ref/blank_circuit.xml`（148367 字节）是**解密官方空白电路**得到的，
`Elements` 只有一个空 `CiCircuit`，`Objects` / `ReferencedComponents` 都是空的。

**这是最干净的注入基底** —— 所有对象都从这里长出来，
不会带入任何样例电路的残留（图层设置、视图状态、栅格等都在，正好是我们需要的）。

`out/ref/own_blank.ms14` 是用自研压缩器重打包它的结果，**Multisim 能正常打开**。

---

## 9. 常用查询套路

```python
import sys; sys.path.insert(0, "tools")
import msmodel

c = msmodel.Circuit.from_xml_file("corpus/samples/PowerSupply.xml")

# 所有元件
for comp in c.components():
    print(comp["refdes"], comp["family"], comp["part"], c.position(comp["ciid"]))

# 引脚坐标（用来连线）
info = c.pin_info(ciid)     # {"1": {"xy": (x, y), "def_ids": [...], ...}, ...}

# 网络
for n in c.nodes():
    print(n["name"], "连了", len(n["ports"]), "个引脚")

# 摘要
print(c.summary())
```
