# 直流静态电路：为什么"取不到数"是个假问题

> 版本：v0.5.0
> 结论先说：**直流电路从来没有取不到数**。真正坏掉的是 COM 的**调用顺序** ——
> 在 `run()` 之后、`read()` 之前多调一次 `EnumOutputs()`（也就是 `circ.probes()`），
> 会让之后所有 `GetOutputData()` 返回 `E_FAIL`。

---

## 1. 现象

`POWER_SOURCES / DC_POWER` + `RESISTOR_VIRTUAL` + `GROUND` 的最小电路，
`.ms14` 生成正常（28156 字节），Multisim 也能打开，探针在 open 时就注册成功：

```
outputs: ['V(探针1)', 'V(探针2)']
```

但接下来每一步读数都是：

```
read(V(探针1)) 失败: (-2147467259, '未指定的错误', None, None)
read(V(探针2)) 失败: (-2147467259, '未指定的错误', None, None)
```

`-2147467259` 是 `0x80004005`，即 `E_FAIL`。`transient` 和 `DoDCOperatingPoint`
**两条路一样失败**，所以最初判断"是分析类型选错了"，这个判断是错的。

### 被推翻的旧结论

`tools/build_acceptance.py` 头注释里记过一条：

> 纯电阻回路没有动态元件，瞬态在毫秒级算完，`SimState` 立刻回 `stopped`，
> `EnumOutputs()` 为空。

这次实测证明**这条是误诊**。`out/dc/bisect_P1.json` ~ `P3.json` 用的就是
`DC_POWER + R + GND`，`transient` 跑满 **1200 点**：

```json
"V(探针1)": { "n": 1200, "min": 4.999999999999999, "max": 5.000000000000001 }
"V(探针2)": { "n": 1200, "min": 0.0, "max": 0.0 }
```

纯电阻回路的瞬态完全正常。当年"要并一个 1pF 电容才跑得起来"的绕法，
绕的不是仿真引擎，是调用顺序。**不需要再并任何假元件。**

---

## 2. 怎么定位的

### 2.1 先确认文件本身没问题

拿仓库里**早就验证过**的 `tools/p18_run2.py`（v0.1.0 时期的脚本，一个字没改）
去读同一个 `out/dc/dc_min.ms14`：

```
V(探针1) = 5.0
V(探针2) = 0.0
```

读得出来。所以排除掉：`.ms14` 结构错、连线错、探针绑定错、探针命名冲突。
问题在**我的实验脚本**里。

### 2.2 二分：一次只加一个 COM 调用

`out/dc/bisect.py`，每个 case 单独起一个进程跑（同一进程里连跑多个 case，
`stop()` 之后状态会退化，结论不可信）：

| case | 相对 P0 多了什么 | 枚举到的输出 | 读数 |
|---|---|---|---|
| P0 | 基线（open → request → run → read） | 2 | 正常 |
| P1 | run **之前**多一次 `EnumOutputs` | 2 | 正常 |
| P2 | 多一次 `EnumComponents` | 2 | 正常 |
| P3 | 多一次 `RLCValue` | 2 | 正常 |
| **P4** | **run 之后、read 之前多一次 `EnumOutputs`** | **0** | **全部 E_FAIL** |

`P4` 的原始记录（`out/dc/bisect_P4.json`）：

```json
"got": [],
"read": {
  "V(探针1)": { "err": "(-2147467259, '未指定的错误', None, None)" },
  "V(探针2)": { "err": "(-2147467259, '未指定的错误', None, None)" }
}
```

`got` 是空的 —— 不是"读失败"，是**枚举本身返回了 0 个输出**，
连带把已经注册好的输出缓冲也作废了。所以表现像"电路死了"，其实是句柄死了。

---

## 3. 铁律

> **`EnumOutputs` 只在 open 之后调一次，把名字缓存下来。
> 从 `run()` / `DoDCOperatingPoint()` 到读完数据之间，一次都不要碰。**

落在代码里：

- `tools/ir_sim.py` → `simulate_dc()`：`outs = list(circ.probes())` 只出现一次，
  后面所有地方都用缓存的 `outs`。
- `tools/ir_sim.py` → `simulate()`（v0.4.0 的 AC transient 内核）：本来就是这个写法，
  **一行没改**。
- `tools/dc_run.py`：docstring 里写死了这条铁律。

`tools/nl_run.py` 的打印 `outputs: [...]` 之所以安全，是因为它读的是
`sim_result["outputs"]`（缓存），不是重新枚举。

---

## 4. 两条路都能跑通，读到的数完全一样

同一个文件 `out/dc/dc_min.ms14`（V1=5V, R1=1000Ω）：

| | `transient` | `DoDCOperatingPoint` |
|---|---|---|
| 调用 | `RunSimulation` | `DoDCOperatingPoint(outs)` |
| 每个探针的采样点 | 1200 | **1** |
| `V(in)` | 5.000000 | 5.000000 |
| `V(0)` | 0.000000 | 0.000000 |
| `V_R = V(in) − V(0)` | 5.000000 | 5.000000 |
| `R`（Multisim `RLCValue` 报的） | 1000.0 | 1000.0 |
| `I = V_R / R` | 0.005000 A | 0.005000 A |
| 结果文件 | `out/dc/dc_result_transient.json` | `out/dc/dc_result_dcop.json` |

**为什么选 dcop 做默认**：静态电路没有时间维度，1200 个一模一样的点是浪费；
而且 dcop 直接表达"这是工作点分析"，不会让用户看到一条平的"波形"。
`transient` 保留作为对照 —— 它能证明两条路给的数一致，这本身就是一次交叉验证。

**电流的来源要说清楚**：Multisim 的电压探针只给电压，不给电流。
`I = 0.005 A` 是 `V_R / R`，其中 `V_R` 是探针实测、`R` 是 Multisim 自己
`RLCValue` 报的 1000.0（不是从 IR 抄的）。IR 里写的 1000 和 Multisim 报的 1000
对得上，这件事本身也被检查了。**没有用理想电流探针，也不假装用了。**

---

## 5. 复现

```bash
# 1) 最小电路：只调已验证的 add_part / connect / add_probe_ext
python tools/build_dc.py
#    -> out/dc/dc_min.ms14

# 2) 两条路各跑一次，判定电压/电流
runtime/py32/python.exe -u tools/dc_run.py --mode transient
runtime/py32/python.exe -u tools/dc_run.py --mode dcop

# 3) 中文端到端
runtime/py32/python.exe -u tools/nl_run.py --file examples/nl/dc_5v.txt
```

### 如果哪天又"取不到数"，按这个顺序查

1. 先跑 `tools/p18_run2.py <同一个.ms14>`。它读得出来 → 文件没问题，查你的脚本。
2. 查脚本里 `probes()` / `EnumOutputs` 出现了几次。**必须只有一次，且在 run 之前。**
3. 查是不是同一个进程里跑了好几个 case。一个 case 一个进程。

---

## 6. 这次改了什么、没改什么

**改的：**

- `tools/circuit_ir.py`：`SUPPORTED` 加 `("POWER_SOURCES", "DC_POWER")`；
  `ANALYSES = ("transient", "dc")`；`validate()` 对 `dc` 提前返回
  （静态电路没有时间窗口，不该被 `stop > 0` 之类的规则拦下）。
- `tools/nl2ir.py`：直流源分支从"抛错"改成正常解析；`测量...两端电压` 句式。
- `tools/ir_sim.py`：**新增** `simulate_dc` / `measure_dc` / `theory_dc`。
- `tools/nl_run.py`：拆成 `run_transient` / `run_dc`。
- 新增 `tools/build_dc.py`、`tools/dc_run.py`、`tools/dc_strategies.py`、`out/dc/bisect.py`。

**没改的：**

- `simulate()`（AC transient 内核）、`fit_channels()`、`measure()`、`theory()` —— 一行没动。
- `tools/mssafe.py`、`Assembler.add_part` / `connect` / `add_probe_ext` —— 一行没动。
- `tools/ir_run.py`（v0.3.0 基线）—— 一行没动，回归仍然拿它当基准。

回归证据：`test_mssafe` 4/4；`test_ir_validate` 全过；`test_nl2ir` 59/59；
`ir_run.py examples/rc_lowpass.ir.json` 增益 0.70632 / 相位 −45.06°（与基线 Δ=0.00e+00 / Δ=0.000°）。
