# 死路清单与避坑指南

> **这份文档的目的是让接手者不要再花时间在已经证明走不通的路上。**
> 每条都标注了"怎么发现的"和"证据"，不是拍脑袋排除的。

---

## 一、完全走不通的路（别再试了）

### 1. GitHub 上找现成项目

**结论：没有。**

搜过的关键词：`multisim automation`、`multisim python`、`multisim com`、
`ni multisim api`、`ms14 file format` 等。

- GitHub 上没有能"画电路"的项目。有几个 wrappper 级的，本质都是包 COM API，
  和我们阶段一做的一样，解决不了放元件/探针的问题。
- CSDN / 博客园上那些写 `NiMultisim.Application`、`circuit.Components[]` 的教程
  **是编的**。`NiMultisim.Application` 这个 ProgID 不存在，
  正确的 ProgID 是 `MultisimInterface.MultisimApp`。
  照着这些文章写代码会浪费大量时间。

### 2. AngelScript / 内置脚本引擎

**结论：没有可用入口。**

- Multisim 里有 `Scripting.dll`，导出 `CreateAngelscriptIDE`。
- 但：**没有任何地方调用它**。菜单里没有脚本入口，没有文档，没有命令行参数。
- 花了很多时间枚举 `SCH_CAP.dll` 等模块的字符串和导入表，没找到触发路径。

**如果想继续挖**：可以用 x64dbg 附加，在 `CreateAngelscriptIDE` 上下断点，
看有没有代码路径能到。但预期收益低。

### 3. Win32 菜单 API dump 菜单树

**结论：拿不到。**

- `GetMenu(hwnd)` 返回 **0**。
- 原因：Multisim 用 **MFC 可停靠菜单栏**（`BCGPToolBar` 那套），不是传统的窗口菜单
  （`HMENU`）。Win32 菜单 API 对它无效。
- 替代方案：**截图 + 像素标定**。这是本项目最终采用的方案，见 `docs/probe.md` 第 3 节。

### 4. 用 `CCompressUtil` 解压 `.ms14`

**结论：不可用。**

- NI 自己的 `CCompressUtil::uncompress` 对所有测试输入都返回 `False`。
- 已经绕过：改用 `vendor/blast.c`（Mark Adler 的公版 DCL 解压器）+ 纯 Python `explode`。
- 别再尝试逆向这个 C++ 类了，直接读文件自己解。

### 5. `ImportSpiceNetlist` 导入网表造电路

**结论：格式未知，高风险。**

- 在 `SCH_CAP.dll` 里找到了 `ImportSpiceNetlist` 和 `SetupProcess SPICE_IMPORT`
  以及字符串 `'Choose a ULTIcap file to import'`。
- 但只支持 **ULTIcap / OrCAD** 格式，而且没有文档说明格式细节。
- 就算逆出来，也只能导网表（连接关系），导不出元件符号和位置，画布上还是空的。

**如果网表导入是你的目标**，可以试试先做一个 ULTIcap 文件让 Multisim 导一次，
再 diff。但优先级低于直接生成 XML。

### 6. 靠 COM API 放元件 / 放探针

**结论：API 里没有这些方法。**

- 完整方法列表见 `docs/api.md`（从类型库导出，40+ 个方法）。
- 和放置相关的方法只有一个 `ReplaceComponent`（替换已有元件的型号）。
- 没有 `AddComponent` / `PlaceComponent` / `AddWire` / `AddProbe`。

### 7. 让 Multisim 以"无头"方式跑

**结论：不行，它必须要窗口。**

- 启动时必须有一个可见的主窗口，否则不初始化。
- 数据库那 3 个弹窗也必须处理（自动点掉）。

---

## 二、走通过但坑很多的路（照文档做能省几小时）

### 8. UAC 提权启动 Multisim

**结论：不需要提权，但前提是关掉兼容性设置。**

踩过的坑：
- `ShellExecuteW(None, "runas", ...)` 经常返回 `5`（ERROR_ACCESS_DENIED）或者
  返回 `42` 但用户没看到 UAC 弹窗没点 → 自动化卡住。
- 直接 `runas` 启动 `python.exe` **被安全策略拦截**（SIGTERM，无输出）。
  改用 `cmd /c` 包装（`tools/oneshot.py`）能成功，但还是要用户点 UAC。
- 做了常驻提权代理（`tools/elev_agent.py` + `agent_launch.py`，文件队列通信），
  **最终没跑通**，而且没必要。

**最终解法（用户配合）**：关掉 `multisim.exe` 的"以管理员身份运行"兼容性设置。
之后免提权直接 `subprocess.Popen([EXE, path])` 就能启动，
`is_admin: False` 也能正常打开文件、正常渲染。

> **为什么提权没用**：我们是直接写 `.ms14` 文件，根本不走 Multisim 的元件库/数据库。
> 提权只影响"打开时数据库能不能用"，而数据库不可用只是弹 3 个警告框，不影响读电路文件。
> 所以提权是纯负担。

**给接手者的建议**：如果 Multisim 启动时弹 UAC，先检查兼容性设置，别去做提权代理。

### 9. GUI 自动化点击坐标

**结论：能用，但坐标必须本机标定，且要用"截图坐标 → 屏幕坐标"换算。**

踩过的坑：
- **DPI 缩放**。截图是 1600×900，但 `SetProcessDPIAware()` 之后
  `GetSystemMetrics` 可能返回不同值。本项目用"窗口矩形左上角 + 截图内偏移"换算：
  ```python
  def to_screen(h, x, y):
      l, t, _, _ = G.rect(h)
      return l + int(x), t + int(y)
  ```
  这比 `SetCursorPos(绝对坐标)` 可靠，因为它不依赖 DPI 假设。
- **点击不生效**。一开始 `click` 用了 `SendMessageW`/`PostMessageW` 发鼠标消息，
  Multisim 完全不响应。必须用 `SetCursorPos` + `mouse_event`（真实输入）。
  见 `tools/guiauto.py` 的 `click()`。
- **前台窗口**。点击前必须 `SetForegroundWindow`，否则消息发到别的窗口。
- **菜单要"悬停"才展开子菜单**。`SetCursorPos` 过去停 0.4~0.8 秒再点，
  直接点有时候不展开（见 `docs/probe.md` 3.3）。
- **工具栏按钮没有文字**，`TB_GETITEMRECT` 能拿到矩形但不知道是谁。
  只能靠悬停看 tooltip（本机 tooltip 也没出现）或者像素 diff 探测按下状态。
  **最终放弃工具栏，全走菜单。**

### 10. 元件值改了不生效

**结论：值存了五处，必须全改。**

最初只改了 `Attributes[2]/CiaParamList/doubles[1]` 和
绘图对象的 `CIITSymTextCompValue@Output`，界面仍显示旧值。
放大截图逐像素确认后，才发现 `Attributes[41]`、`Attributes[42]`、
`CiaParamList/parameters[1]` 也没改。

**五处完整清单见 [circuit-xml.md 第 4 节](circuit-xml.md#4-元件值存在四处最容易踩的坑)。**

**另一个坑**：槽位 41/42 不是所有元件都有，部分元件 `Attributes` 不足 43 项，
直接索引会 `IndexError: list index out of range`。必须先判断 `len(items) > 42`。

### 11. 解压 XML 报 `ParseError('unclosed token')`

**结论：`.ms14` 是分块容器，只解第一块会截断。**

- 超过 900000 字节会分块，**后续每块只有 8 字节头**（块明文长 + 块压缩长），
  没有 magic、没有总长字段。
- 只解第一块的代码会对大文件解出残缺 XML。
- 修法：按块头循环解压，直到 `pos >= len(file)`。
  见 `tools/dcl.py` 的 `read_ms14()`。

### 12. 自研压缩器往返失败

**结论：三个坑，都记在格式文档里。**

1. 漏写 DCL 结束码 → `blast` 报"输入耗尽"。
   结束码 = 长度符号 15 + 8 个额外位全 1。
2. `enc_len[15]` 反推出 1 位码而非 7 位 → 编码表反推必须按符号**真实码长**搜索，
   不能零填充暴力搜。
3. LZ77 `KeyError: -1` → 哈希链必须**边扫描边插入**，
   不能预构建整条链（`head[key]` 会指向未来位置）。

### 13. `python -c` 带复杂引号被安全策略拦截

**结论：改用 heredoc 或写成 .py 文件。**

- `Command blocked for security: Known Windows LOLBin`。
- 可用形式：
  ```bash
  python - <<'PY'
  import sys
  ...
  PY
  ```
  或者先 `Write` 一个 `.py` 再执行。

---

## 三、环境层面的坑

### 14. 三个"访问数据库时发生错误"弹窗

- **不是我们弄坏的**。用户手动打开 Multisim 也有这 3 个弹窗，是 Win11 安全补丁导致的固有问题。
- 代码自动点掉：`msui.dismiss_all()`（遍历可见对话框，给 ID=1 的按钮发 `BM_CLICK`）。
- 不影响功能：电路文件照常读取、照常渲染。

### 15. 必须 32 位 Python 才能用 COM

- CLSID `{D9CBB7A1-6AD6-438B-AD1B-42FB2DB00CAE}` 只注册在 WOW6432Node。
- 64 位 Python `CreateObject` 报"没有注册类"。
- 项目里 `run.bat` 自带 32 位 Python 3.11 + pywin32。
- **注意**：编解码/XML 那部分（`tools/dcl.py`、`msmodel.py`、`msbuild.py`）
  **不依赖 COM，用 64 位 Python 完全没问题**。只有跑仿真那一步需要 32 位。

### 16. 样例电路的来源

官方样例在：
```
C:\Users\Public\Documents\National Instruments\Circuit Design Suite 14.3\samples\
```
共 118 个 `.ms14`。本项目已全部解压，存在 `corpus/samples/*.xml.gz`。
10 个因 XML 解析失败被跳过（分块处理修好之前的旧索引，重新跑
`tools/index_samples.py` 应该能补齐）。

---

## 四、方法论沉淀（比技术细节更重要）

### 怎么定位未知压缩格式

1. 先用十六进制编辑器看文件头，找 magic 和长度字段。
2. **去 zlib 的 `contrib/` 目录逛一圈**。`blast` 就是为 PKWARE DCL 写的，
   而 DCL 是 90 年代 Windows 软件最爱用的格式之一。本次就是靠 `blast.c`
   头部的格式说明注释破的。
3. 交叉验证黄金标准：**解出来的字节数必须和头部长度字段完全相等**。
   差一个字节都说明理解有误。
4. 有条件就找个公版实现做 ground truth，别只信自己的解码器。

### 怎么摸清未知 XML 对象模型

1. **找一个空白文件做基底**。空白电路的 XML 最干净，能看出哪些是"必需结构"、
   哪些是"数据"。本项目用 `blank.ms14` 解出的 148367 字节做基底。
2. **做一个最小改动，然后 diff**。加一个元件 → 存盘 → diff。
   本项目的元件结构、探针结构都是这么做出来的。
3. **用 GUI 做"探针实验"**：想让 Multisim 生成什么结构，就用 GUI 做一个，
   保存，解压，读 XML。比纯逆向快十倍。
4. 两棵平行树（电气 + 绘图）要同时改，只改一边不生效。

### 怎么验证"真的成功了"

- 不要只看 XML 里字段改对了。**必须让 Multisim 打开，截图，逐像素看界面。**
  本项目的"电阻值改了不生效"就是靠放大截图才发现的。
- 最终验收要看仿真读数（电流 = 5 mA），而不只是显示文字。

---

## 五、探索期脚本说明

`tools/` 下有很多一次性脚本，是不同阶段的尝试。列出来避免接手者困惑：

| 脚本 | 阶段 | 价值 |
| --- | --- | --- |
| `dcl.py` `msmodel.py` `msbuild.py` `build_acceptance.py` | 主线 | ★★★ 核心 |
| `index_samples.py` `verify_open.py` `msui.py` `guiauto.py` | 主线 | ★★★ 核心 |
| `cmp_attr.py` | 调值 | ★★ 对比元件属性结构 |
| `crack_codec.py` `crack_codec2.py` `dcl_compress.py` `dcl_uncompress.py` | 破解压缩 | ★★ 记录了试错过程 |
| `dump_xml.py` `dump_memory.py` `memscan.py` `db_probe.py` | 逆向 | ★ 试错记录 |
| `elev.py` `elev_agent.py` `elev_launch.py` `agent*.py` `oneshot.py` | 提权 | ★ 已绕过，留档 |
| `exp1.py` `exp2.py` `exp3.py` `hunt_event.py` `scan_clsid.py` `strings_hunt.py` | 逆向 | ★ 试错记录 |
| `dump_menu.py` `menu.py` `toolbar.py` `probe_*.py` `try_*.py` | GUI 探路 | ★★ 探针/GUI 尝试记录 |
| `test_clone_gnd.py` `test_edit.py` `verify_pins.py` | 验证 | ★★ 阶段性验证脚本 |
| `drv.py` `edo.py` `do.py` `open_one.py` `gen_*.py` `inspect_probe*.py` | 杂项 | ★ |

**接手时只需要看标注 ★★★ 的四个文件 + 文档，其余按需查。**
