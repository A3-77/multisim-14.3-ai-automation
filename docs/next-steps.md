# 给接手者的路线图（v0.5.0 起）

> 上一版写于 v0.4.0，P0（直流源）已经做完了。
> 这一版按 **v0.5.0 的实际状态**重排，只写还没做的事。
>
> 已完成（不要再重做）：`.ms14` 编解码 / `mssafe` 无损往返 / 元件克隆 /
> 纯代码探针 / 统一 `add_part` / RC 三点频响 / Circuit IR + 校验 /
> 中文 → IR 端到端 / **直流静态电路（两条路，见 `docs/dc-static.md`）**。

---

## P1 —— MCP Tool API：把工具链变成"能被调用"的东西

### 为什么排第一

现在这条链是**脚本**，不是**工具**：

```
nl_run.py --file xxx.txt
```

每一步（解析、编译、仿真、读数）都焊死在一个脚本里，外面的人只能整条跑。
LLM 或别的程序想用，只能读代码猜参数。**先把接口定型，再谈接 LLM。**

### 做什么

按"一个动作一个工具"拆，参数只接受 Circuit IR 里的概念，不接受 Multisim 概念：

| 工具 | 输入 | 输出 |
|---|---|---|
| `create_circuit` | `name` | `circuit_id` |
| `add_component` | `circuit_id`, `refdes`, `family`, `part`, `value`, `x?`, `y?` | 引脚列表 |
| `connect` | `circuit_id`, `pins: [(refdes, pin)]`, `net_name?` | `net_id` |
| `add_probe` | `circuit_id`, `net_id`, `kind="V"` | `probe_id` |
| `simulate` | `circuit_id`, `analysis: transient\|dc`, `stop?`, `sample_rate?` | `sim_id` |
| `measure` | `sim_id` | 每通道的拟合值 / 均值、`rlc` |
| `get_waveform` | `sim_id`, `channel?` | 采样点数组 |

关键约束：

- **无状态服务端**：`circuit_id` / `sim_id` 是句柄，内部映射到 IR 文件路径。
  IR 本身就是可序列化的状态，不需要额外数据库。
- **错误一律结构化返回**，不抛裸异常。`validate()` 的 `issues` 列表直接就是
  `{"ok": false, "issues": [...]}`，现在已经有这个形状了。
- **一次仿真一个 Multisim 进程**。`EnumOutputs` 只能调一次这条铁律
  （`docs/dc-static.md`）必须在 `simulate` 里封死，不能让调用方碰。

### 怎么算完成

`tools/mcp_server.py` 起一个 stdio MCP server，用下面这段等价于
"5V 串 1kΩ 接地"的调用序列，拿到 5.0 V / 5 mA：

```
create_circuit("dc_5v")
  -> add_component(cid, "V1", "POWER_SOURCES", "DC_POWER", 5)
  -> add_component(cid, "R1", "RESISTOR", "RESISTOR_VIRTUAL", 1000)
  -> add_component(cid, "GND1", "POWER_SOURCES", "GROUND")
  -> connect(cid, [("V1","1"), ("R1","1")], "in")
  -> connect(cid, [("V1","2"), ("GND1","1"), ("R1","2")], "0")
  -> add_probe(cid, "in"); add_probe(cid, "0")
  -> simulate(cid, "dc")  -> measure(sid) -> 5.0 / 5.0 / 0.005
```

而且 `nl_run.py` 要改成**调这套工具**，不是自己再写一遍 —— 否则就是两套逻辑。

---

## P2 —— 并联 / 多支路拓扑

### 为什么

"RC 低通"是串联链，一句话就够。真实电路基本都有并联（分压 + 旁路电容、
共射放大的偏置网络）。现在 `nl2ir` 见到"并联"直接报错。

### 已知事实

- v0.2.0 已经**证伪**"必须有 junction 结点对象"：3 引脚中点不需要任何结点，
  实测读到 2.5 V（`docs/deadends.md`）。
- 所以拓扑表达不缺底层能力，缺的是**布局算法** —— 现在的坐标是给串联链写死的。

### 做什么

1. IR 层不用改：`nets` 本来就是"网络 → 引脚列表"，能表达任意拓扑。
2. 写一个布局器：按"源在左、地在下、元件按网络分层"排，输出每个元件的
   引脚质心坐标。先只支持两三个固定模板（分压、旁路电容、T 型网络）。
3. `nl2ir` 加"并联 / 并在...两端 / 和...并联"的句式，映射到对应模板。

### 怎么算完成

分压器 + 旁路电容（`R1/R2/C1`）用一句话生成，Multisim 里中点电压对上
`R2/(R1+R2)`，交流下旁路电容让增益随频率下降。

---

## P3 —— 元件库扩容

### 问题

现在只能克隆"样例库里出现过"的 `(family, part)`。多引脚元件（运放、555）
的引脚重映射还没验证过，`add_part` 目前只对 2 引脚 + 地做过验收。

### 方向

1. 从 `corpus/samples_index.json` 挑一个运放样例，跑通 `add_part` 的多引脚路径
   （重点：`PortID` 重映射、引脚名是否唯一）。
2. 建 `templates/` 目录，把每种用到的元件子树存成模板，摆脱"必须找到 donor 文件"。
3. 单位哈希表：`&UNI<值>_uc<hash>` 的 hash 算法未知，现在是"继承旧值后缀"绕过的。

---

## P4 —— LLM 外壳（放在最后，不要提前做）

规则解析器已经能覆盖受控句式。LLM 的正确位置是**它前面**：

```
自由中文
  ↓  LLM：只做"规范化"，不产出 IR
受控句式（"1V 1kHz 正弦源，经过 1kΩ 电阻后接 159nF 电容到地，..."）
  ↓  nl2ir（确定性、可测试）
Circuit IR
```

失败时把 `NLParseError.issues` 回灌给模型让它重写。**不要让 LLM 直接写 IR**，
否则"同一句话两次生成不同电路"这个问题会一直跟着你。

---

## 附：一句话状态

```
✅ .ms14 编解码（纯 Python，零依赖）
✅ 从空白电路生成元件 + 连线 + 探针，Multisim 正常打开、真实仿真
✅ RC 低通三点频响全部对上理论
✅ Circuit IR + 编译前校验（26 项反向用例）
✅ 中文 → IR → 仿真（59 项解析用例；1 kHz / 2 kHz 两个电路真机验收）
✅ 直流静态电路（transient 与 DC Operating Point 两条路读数一致）
⬜ MCP Tool API
⬜ 并联 / 多支路布局
⬜ 多引脚元件（运放 / 555）
⬜ LLM 外壳
```
