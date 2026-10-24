# 电压探针

探针是整个项目的**卡点**，也是验收标准里明确要求的一项
（"在电阻两端放电压探针并保存"）。

探针之所以关键，还有第二个原因：**COM API 取仿真数据必须靠探针**。
`EnumOutputs()` 枚举的是图纸上的探针（`V(Probe1)` 这种名字），没探针就取不到数，
报错"输出未找到。"——所以探针是"能仿真"的前置条件。

---

## 1. 两种探针，别搞混

| 类型 | 出现在 | 类名 | 说明 |
| --- | --- | --- | --- |
| 老式探针 | 官方样例电路（`corpus/samples/`） | `CiProbeComp` + `CIITIMeterSymbolComp` | 靠 `NetName` 属性显式绑网络 |
| **新式探针** | Multisim 14.3 GUI 新放的 | **`CiProbeExtComp` + `CIITProbeExtComponent`** | **没有显式网络引用** |

**本项目生成电路时该抄哪种？抄新式（`CiProbeExtComp`）**，因为它是 14.3 当前版本的行为。
老式结构在官方样例里能见到（`Power Conversion__AC-DC__ControlledRectifier.ms14` 等），
可以对照参考，但直接抄老式的 `NetName` 机制在新版里不一定生效。

---

## 2. 新式探针完整结构（实测，来自 GUI 放置后保存的文件）

完整 XML 见 **`out/ref/probe_ext_full.xml`**（这是本项目最珍贵的参考样本之一）。
下面是要点。

### 2.1 电气对象：`CiProbeExtComp`（放在 `Elements` 里）

```xml
<Item CiID="234011048" Class="CiProbeExtComp">
  <CiProbeExtComp Class="CiProbeExtComp"
      LocalName="&amp;UNI_uc263a294881"
      SymCompID="237472448"
      InstanceID="{52C703E0-D6B1-4396-8069-ABFDF1756258}"
      Circuit="233092544">
    <Attributes>
      <Item /><Item /><Item /><Item />
      <Item><CiaCollString Class="CiaCollString"><strings>
        <Item Value="" /> × 7
      </strings></CiaCollString></Item>
      <Item><CiaCollString Class="CiaCollString"><strings>
        <Item Value="" /> × 4
        <Item Value="&amp;UNI_uc263a29488%d" />
      </strings></CiaCollString></Item>
    </Attributes>
    <Ports />                          <!-- 空的！见第 4 节 -->
  </CiProbeExtComp>
</Item>
```

注意 `Attributes` 只有 6 个槽，且大多是空 `CiaCollString` ——
**探针不像元件那样靠 `Attributes[2]` 存参数**，它的配置全在绘图对象的
`DefaultInstrumentProperties` 里。

### 2.2 绘图对象：`CIITProbeExtComponent`（放在 `Components/CODComposite/Objects` 里）

```xml
<Item ID="237472448" Class="CIITProbeExtComponent">
  <CIITProbeExtComponent Class="CIITProbeExtComponent"
      instID="0" Stretchable="1" Moveable="1" ...
      Layer="24" BgColor="11862015"
      Transformer-M20="558" Transformer-M21="333"      <!-- 位置 -->
      Hidden="0" UniqueID="1" Direction="0" Position="1"
      InfoBoxText="&amp;ASC V: --  V(p-p): --  V(rms): --  V(dc): --  V(freq): -- "
      ShowInfo="1" AutoResize="1" InfoBoxOffsetX="6" InfoBoxOffsetY="40"
      FileDataPackageID="&amp;ASCX_e278ac0"
      Font-Height="-9" Font-FaceName="&amp;ASCArial"
      CiProbeExtComp="234011048">                        <!-- 回指电气对象 -->
    <DefaultInstrumentProperties>
      <CDataElementMap Class="CDataElementMap"><MapData>
        <Element Key="&amp;ASCNI_EWB_SHOW_WINDOW_STATUS">...</Element>
        <Element Key="&amp;ASCNI_EWB_DIALOG_STATUS">...</Element>
        <Element Key="&amp;ASCNI_EWB_SIMULATION_ALLOW">
          <CDataElement Class="CDataElement" Type="2" Data="1" />
        </Element>
        <Element Key="&amp;ASCNI_EWB_DATABASEDATA_EXT">
          <!-- 超长的量测项定义：V/V(p-p)/V(dc)/V(rms)/V(freq)/V(period)/I/... -->
          <CDataElement Class="CDataElement" Type="5" Data="&amp;ASCV2.0[]_22[]_ V[]]_1[]]..." />
        </Element>
        <Element Key="&amp;ASCNI_EWB_COMPHANDLE_EXT">
          <CDataElement Class="CDataElement" Type="1" Data="237472448" />
        </Element>
        <Element Key="&amp;ASCInfoBoxSizeX"><CDataElement ... Data="98" /></Element>
        <Element Key="&amp;ASCInfoBoxSizeY"><CDataElement ... Data="76" /></Element>
        <Element Key="&amp;ASCNI_EWB_REALTED_ANALYSIS_DATA">...</Element>
      </MapData></CDataElementMap>
    </DefaultInstrumentProperties>
  </CIITProbeExtComponent>
</Item>
```

**可直接整段复制**（`copy.deepcopy`）再改这几个字段：
- `Transformer-M20/M21` → 位置
- `CiProbeExtComp` → 新的电气对象 CiID
- `NI_EWB_COMPHANDLE_EXT/Data` → 新的绘图对象 ID
- `InstanceID` → 新 GUID
- `LocalName` / `InfoBoxText` → 显示名与信息框文字

### 2.3 必须在 `CiCircuit` 里注册（新列表！）

这是**和老式探针最大的区别**：`CiCircuit` 下多了一个 `ProbeExts` 列表：

```xml
<CiCircuit Class="CiCircuit" LocalName="">
  <Attributes/>
  <Models>      <Item CiID="233513752"/> </Models>
  <Nodes>       <Item CiID="233355872"/> <Item CiID="233354936"/> </Nodes>
  <Probes/>                          <!-- 老式探针走这里，空着 -->
  <ProbeExts>                        <!-- ★ 新式探针走这里 -->
    <Item CiID="234011048"/>
  </ProbeExts>
  <CompAddRefs/>
  <Components>   <Item CiID="..."/> × 3 </Components>
</CiCircuit>
```

**只把对象塞进 `Elements` / `Objects` 而不往 `ProbeExts` 里加 `Item`，探针不会出现。**

---

## 3. GUI 放置流程（已跑通，可复现）

当纯代码路线还没走通时，这条兜底路线是能用的：
让 Multisim 自己放探针、自己保存，我们再解析保存结果。

### 3.1 菜单坐标（本机 1600×900 实测，Multisim 窗口在 (20, 74)）

```
菜单栏            y = 43
  文件(F)         x = 55
  绘制(P)         x = 178      ← 要用的
绘制菜单          x = 200
  Probe 子菜单     y = 85       ← 悬停展开，点击进入
电压探针          (427, 87)    ← 子菜单第一项
目标网络          画布上的点
```

### 3.2 代码

```python
import sys, time, ctypes
sys.path.insert(0, "tools")
import msui, guiauto as G
u = ctypes.windll.user32

h = msui.launch("out/ref/with_probes.ms14")     # 启动 + 自动点掉 3 个数据库弹窗

def arm():
    G.click(178, 43); time.sleep(0.7)           # 绘制
    u.SetCursorPos(200, 85); time.sleep(0.4)    # 悬停 Probe
    G.click(200, 85);  time.sleep(0.7)          # 进入 Probe 子菜单
    G.click(427, 87);  time.sleep(0.7)          # 电压探针

arm()
G.click(725, 436); time.sleep(0.8)              # 点到 net1（V1+ → R1 左端）
arm()
G.click(725, 481); time.sleep(0.8)              # 点到 net0（R1 右端 → GND）
```

### 3.3 踩坑记录（重要）

1. **放置后不会立刻成探针**，而是弹一个下拉框让选量测项
   （`V / V(p-p) / V(rms) / V(dc) / V(freq) / V(period)`，见 `docs/shots/03_*.png`）。
   必须点掉或选一项，探针才落地。**这一步没做的话保存出来是 0 个探针**
   （`CiProbeExtComp` 数量为 0）—— 本项目最早一次保存就栽在这里。
2. **`Ctrl+S` 有时不触发保存**（焦点在菜单上时）。可靠做法：
   先点一下画布空白处拿焦点，再 `Ctrl+S`；或者走 文件(F) → 保存(S) 菜单
   （本机坐标 `(55,43)` → `(100,204)`）。
3. **工具栏按钮不可靠**。Multisim 的仪表工具栏是 `BCGToolBar`，
   我们用 `TB_BUTTONCOUNT` / `TB_GETITEMRECT` 能枚举出按钮矩形，
   但按钮没有文字、ID 也对不上菜单命令，点击行为也不稳定。
   **走菜单比走工具栏可靠得多。**
4. **`GetMenu(hwnd)` 返回 0**，Multisim 用 MFC 可停靠菜单栏，不是窗口菜单，
   没法用 Win32 菜单 API dump 菜单树。只能靠截图 + 像素标定。

### 3.4 保存后怎么验证

```python
import sys; sys.path.insert(0, "tools")
import dcl, xml.etree.ElementTree as ET
xml, _ = dcl.read_ms14("out/ref/with_probes.ms14")
t = ET.fromstring(xml)
print(len(list(t.iter("CiProbeExtComp"))), "个探针")   # 期望 ≥ 1
```

---

## 4. 未解之谜：探针怎么绑定网络？（接手第一优先）

这是**唯一挡住"纯代码生成探针"的问题**，我们把已知事实列清楚：

### 已知

- `CiProbeExtComp/Ports` 是**空的**（`<Ports />`）。老式探针那套
  "Ports 里挂引脚"的机制，新式探针**不用**。
- 探针绘图对象里**没有任何** `ConnectList` / `Connect1` / `Node` / `NetName` 属性。
- 探针的 CiID 在整个文件里只出现 3 次：
  1. `Elements` 里的 `Item CiID=`
  2. `CiCircuit/ProbeExts/Item CiID=`
  3. 绘图对象的 `CiProbeExtComp=` 回指
  → **没有任何一处引用网络 CiID。**
- 网络 CiID（`233355872` = net1）在文件里出现 5 次，全在
  `CiNode` 自身、`CiPort/Nodes` 回指、`CIITLinkComp@Node`、
  `CiCircuit/Nodes` 这些**正常位置**，与探针无关。
- 文件里确实有 `CSCH_CAPVirtualComponentPin@lastnet="&ASC1"`
  这种记录，但它在 `CIITHierRefDesManager/ComponentPins` 下，
  是**按元件的引脚**记的（每个元件一份），看起来是 RefDes 管理器的缓存，
  不是探针的绑定。

### 推论与待验证的假设

按可能性排序：

1. **几何推断**：Multisim 加载时按探针绘图对象的位置（`Transformer-M20/M21`）
   找最近的点/线，自动吸附到网络上。→ 验证方法：手工改 `with_probes.ms14` 里探针的
   `M20/M21` 到另一个位置，存盘后看 Multisim 把它连到哪个网。
2. **存在我们还没找到的存储位置**。→ 验证方法：
   用 `dcl.read_ms14` 解出 `with_probes.ms14` 后，做一次**全文本 diff**
   （和放探针前的 `acceptance.ms14` 比），列出所有新增/变化的元素。
   本项目已经做过一次按 Class 计数的 diff（见下），但没做逐元素 diff。
3. **存在独立的探针配置段**（比如某个 `Extension` / `InstrumentData` 节点）。
   文件里新增了 `InstrumentData`、`DefaultInstrumentProperties`、
   `CCircuitParamSheetGroupExtension`、`CLayerViewState`(43 个) 等一堆节点，没逐个查。

### 已经做过的 diff（按 Class 计数，可直接复用）

对比"放探针前"（`out/ref/acceptance.ms14`）和"放探针后"（`out/ref/with_probes.ms14`），
新增的元素类型：

```
CiProbeExtComp                0 → 2      ← 探针本体
CIITProbeExtComponent         0 → 2      ← 探针绘图对象
CIITPinConnectorComp         15 → 20     ← 多出 5 个（疑似探针的连接点）
CSCH_CAPVirtualComponentPin   0 → 5      ← 多出 5 个（疑似探针的虚拟引脚）
CIITLinkComp                  6 → 12     ← 多出 6 条（探针自带的引线？）
CODNodeTextComp               0 → 9
CLayerViewState               0 → 43
CDataElement                  0 → 34
CIITHierRefDes / Info         0 → 3
InstrumentData                0 → 1
...
```

> **`CIITPinConnectorComp` 多出 5 个 + `CIITLinkComp` 多出 6 条，很可疑。**
> 下一步应该先查这 5 个新增的 `CIITPinConnectorComp` 挂在哪个对象下、
> 它们的 `ConnectList` 指向什么 —— 这很可能就是探针与网络的连接点。
> （本项目的 `CIITProbeExtComponent` 里没搜到 Pin 相关标签，所以它们应该在别处。）

---

## 5. 老式探针参考（官方样例里现成的）

`corpus/samples/` 里带探针的样例（实测有 `CiProbeComp` 的）：

- `Power Conversion__AC-DC__ControlledRectifier.ms14`
- `Power Conversion__AC-DC__ControlledThreePhaseRectifier.ms14`
- 其他若干

老式结构靠 `CIITIMeterSymbolComp@NetName` 显式绑网络：

```xml
<CIITIMeterSymbolComp ... NetName="&amp;ASC5" ToolTip="..." Direction="..."
                      FileDataPackageID="..." />
```

**注意**：这是老格式。新版 GUI 放出来的探针已经不用 `NetName` 了。
但老式结构至少证明了"探针可以显式绑网络"，如果新式的几何推断假设不成立，
可以试着给新式探针补一个 `NetName` 看 Multisim 认不认。

---

## 6. 小结：下一步该做什么

按优先级：

1. **逐元素 diff** `acceptance.ms14` vs `with_probes.ms14`，重点查那 5 个新增的
   `CIITPinConnectorComp` 和 6 条新增的 `CIITLinkComp` 挂在哪、指向谁。
2. 如果找到连接点 → 实现纯代码探针克隆（照抄 `probe_ext_full.xml` + 改位置 + 挂连接点）。
3. 如果没找到 → 验证"几何推断"假设（改 `M20/M21` 看保存结果）。
4. 探针搞定后 → 用 COM API 在自建电路上跑仿真，验证 R1 电流 = 5 mA。
