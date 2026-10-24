# 代码架构

## 分层

```
┌─────────────────────────────────────────────────────────┐
│  build_acceptance.py        验收电路生成脚本（示例入口）   │
│  cli.py / demo.py           COM 路线：仿真、扫参、导数据   │
├─────────────────────────────────────────────────────────┤
│  msbuild.py   Assembler    装配器：克隆元件 + 连线 + 保存  │
│  msmodel.py   Circuit      对象模型：查/改元件/引脚/网络   │
├─────────────────────────────────────────────────────────┤
│  dcl.py        read_ms14 / write_ms14 / explode / implode │
│                .ms14 容器 + PKWARE DCL 编解码             │
├─────────────────────────────────────────────────────────┤
│  msui.py / guiauto.py       GUI 自动化（启动/点击/截图）   │
│  verify_open.py             启动 Multisim 验证文件能打开   │
└─────────────────────────────────────────────────────────┘
```

**依赖方向严格向下**：上层不认识下层的实现细节。
`dcl.py` 不认识 XML，`msmodel.py` 不认识 GUI。

---

## 核心文件详解

### `tools/dcl.py` —— 格式层（零依赖，最关键）

| 函数 | 作用 |
| --- | --- |
| `explode(data, pos=0)` | 解一段 DCL 流 → `(明文 bytes, 消耗字节数)` |
| `implode(data, dict_=6, matches=True)` | 压成 DCL 流 |
| `read_ms14(path)` | 读 `.ms14` → `(明文 XML bytes, 头部信息 dict)` |
| `write_ms14(path, xml, ...)` | 明文 XML → `.ms14`（自动分块） |

独立运行可自检：
```bash
python tools/dcl.py out/ref/acceptance.ms14
# 输出解出字节数、头部信息、两种压缩模式的往返结果
```

**为什么重要**：这是整个项目唯一无法绕过的一层。
上面所有功能都建立在"能读写 `.ms14`"之上。

### `tools/msmodel.py` —— 对象模型层

`class Circuit`，一个实例 = 一个已解析的电路。

| 方法 | 作用 |
| --- | --- |
| `Circuit.load(path)` / `from_xml_file(path)` | 从 `.ms14` / 明文 XML 构造 |
| `save(path)` | 写回 `.ms14` |
| `components()` / `find(refdes)` | 枚举 / 按位号找元件 |
| `ident(comp)` | 取 `(family, part)` |
| `params(comp)` / `set_param(comp, idx, v)` | 读 / 改 `CiaParamList` |
| **`set_value_by_refdes(refdes, value)`** | **改元件值并同步全部五处副本** |
| `symbol_of(ciid)` / `position(ciid)` / `translate(ciid, dx, dy)` | 绘图对象 |
| `set_refdes(ciid, refdes)` / `set_value_text(ciid, text)` | 位号 / 值文字 |
| `ports()` / `nodes()` | 引脚 / 网络 |
| **`pin_info(ciid)`** | **引脚绝对坐标（连线必需）** |
| `new_id()` | 分配新 CiID（8 的倍数） |
| `summary()` | 人类可读摘要 |

`eng(value)` / `_num_str(value)` 是数值格式化工具：
`1000 → "1k"`、`"1000."`。规则来自 108 个样例的实测统计。

### `tools/msbuild.py` —— 装配层

| 类 | 作用 |
| --- | --- |
| `Donor(circuit, refdes)` | 从已有电路抽取一个元件模板（电气 + 绘图 + 引脚 + 模型 + 引脚定义） |
| `Assembler()` | 以空白电路为基底，往里加元件 |

`Assembler` 的方法：

| 方法 | 作用 |
| --- | --- |
| `add(donor, x, y, refdes, params)` | 克隆元件到 `(x, y)`，返回 `(新CiID, [(引脚CiID, 引脚名)...])` |
| `connect(ports, name)` | 建网络节点，把引脚用导线串起来 |
| `wire(node_id, a, b, color)` | 两个引脚之间画一条正交导线 |
| `save(path)` | 保存 |

**克隆时做的事**（少任何一件都会出问题）：
1. `deepcopy` 元件的电气 `Item`，换新 `CiID`
2. `CiComponent@Circuit` 指向新电路，`InstanceID` 换新 GUID
3. `deepcopy` 模型 `Item`，换新 `CiID`，`CiModel@Scope` 指向新电路，
   往 `CiCircuit/Models` 追加
4. `deepcopy` 每个引脚 `Item`，换新 `CiID`，`CiPort@Component` 指向新元件，
   **清空 `Nodes`**（避免继承旧网络的引用）
5. `deepcopy` 绘图 `Item`，换新 `ID`，把所有 `CiComponent == 旧CiID` 的改成新的
6. **平移所有 `Transformer-M20/M21`**
7. **复制并平移 `ReferencedComponents` 里的 `CODPinComp` 定义**，
   把 `ConnectList/Item@ID` 改指向新定义
8. 往 `CiCircuit/Components` 追加
9. 设位号、设参数值（`set_value_by_refdes` 同步五处）

### `tools/build_acceptance.py` —— 验收电路脚本

最完整的"从零造电路"示例，**建议先读这个文件再读 `msbuild.py`**。

```python
donor = msmodel.Circuit.from_xml_file("corpus/samples/LabVIEW Multisim API Toolkit__SPICE Command Line__SPICE Command Line.xml")
a = msbuild.Assembler()

dv = msbuild.Donor(donor, "V2")
v1, v1_ports = a.add(dv, x=360.0, y=300.0, refdes="V1")
a.c.set_value_by_refdes("V1", 5.0)

dr = msbuild.Donor(donor, "R1")
r1, r1_ports = a.add(dr, x=520.0, y=300.0, refdes="R1")
a.c.set_value_by_refdes("R1", 1000.0)

gnd_ref = [c for c in donor.components() if c["part"] == "GROUND"][0]["refdes"]
dg = msbuild.Donor(donor, gnd_ref)
g1, g1_ports = a.add(dg, x=520.0, y=420.0)

n1 = a.connect([(v1, "1"), (r1, "1")], name="1")     # V1+ → R1 左
n0 = a.connect([(v1, "2"), (r1, "2"), (g1, "1")], name="0")  # V1- → R1 右 → GND
a.save("out/ref/acceptance.ms14")
```

### `tools/msui.py` + `tools/guiauto.py` —— GUI 自动化

`guiauto.py` 是 Win32 原语：
`enum_windows()` / `find(cls, ...)` / `rect()` / `foreground()` /
`click(x, y)` / `hotkey(...)` / `press(vk)` / `screenshot(hwnd, path)` /
`screenshot_screen(path)` / `visible_dialogs()`

`msui.py` 是高层封装：
`launch(path)`（启动 + 点弹窗 + 等主窗口 + 置前台）/
`dismiss_all()` / `click_img(h, x, y)`（截图坐标 → 屏幕坐标）/
`shot(h, name)` / `to_screen(h, x, y)` / `kill()`

### `tools/verify_open.py` —— 验证脚本

```bash
python tools/verify_open.py <ms14文件> <输出json>
```

启动 Multisim 打开指定文件，自动点掉弹窗，截图，按窗口标题判断是否打开成功。
输出 JSON：`{"opened": true, "hwnd": ..., "dialogs": [...], "shot": "..."}`。

### `tools/index_samples.py` —— 语料库索引

```bash
python tools/index_samples.py
```

扫描官方样例目录，解压每个 `.ms14`，抽取元件清单，写 `corpus/samples_index.json`
并把明文 XML 缓存到 `out/samples/`。

**语料库已经生成好了**（`corpus/samples/*.xml.gz`），一般不用重跑。

---

## 数据流

### 生成电路

```
build_acceptance.py
   │
   ├─► msmodel.Circuit.from_xml_file(blank_circuit.xml)   # 空白基底
   │
   ├─► msmodel.Circuit.from_xml_file(样例明文)             # 元件来源
   │
   ├─► msbuild.Donor(donor, "V2")                          # 抽模板
   ├─► msbuild.Donor(donor, "R1")
   ├─► msbuild.Donor(donor, gnd_ref)
   │
   ├─► Assembler.add(...) × 3                              # 克隆 + 平移 + 改值
   ├─► Assembler.connect(...) × 2                          # 建网络 + 画导线
   │
   └─► Circuit.save(path)
          └─► dcl.write_ms14(path, xml)
                 └─► dcl.implode(...)  ← PKWARE DCL 压缩
```

### 验证

```
verify_open.py
   └─► msui.launch(path)
          ├─► subprocess.Popen([multisim.exe, path])
          ├─► dismiss_all()          # 点掉 3 个数据库弹窗
          └─► find_main()            # 等主窗口（标题含 "["）
   └─► guiauto.screenshot(hwnd, "out/shots/verify.png")
```

### 探针（GUI 兜底路线）

```
msui.launch(with_probes.ms14)
   └─► 菜单点击序列：绘制 → Probe → 电压探针 → 点网络
   └─► 文件 → 保存
   └─► dcl.read_ms14(...) → 解析 CiProbeExtComp 结构
```

---

## 目录约定

| 路径 | 内容 | 是否入库 |
| --- | --- | --- |
| `tools/` | 全部脚本 | ✅ |
| `vendor/` | `blast.c/h` + `dcltool.c` | ✅ |
| `corpus/` | 108 个样例明文 XML（gzip）+ 索引 | ✅ |
| `out/ref/` | 关键产物：空白基底、验收电路、带探针版本、探针 XML | ✅ |
| `docs/` | 文档 + 关键截图 | ✅ |
| `out/` 其余 | 探索期中间产物 | ❌（本地留着备查） |
| `samples/` | 原始 `.ms12` 示例 | ✅ |
| `runtime/` | 32 位 Python + pywin32 | ❌（.gitignore） |

`out/` 下除 `ref/` 外的文件是探索过程的中间产物（截图、候选文件、内存转储等），
保留在本地但不入库，避免仓库膨胀。
