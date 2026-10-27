| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=rc_lpf_1k_100n_2k | ok | 4 ms |
| 2 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 | **MISSING_PARAMETER** ⚠注入 | 16 ms |
| 3 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 3 ms |
| 4 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 parameters={"frequency": 2000} | ok | 14 ms |
| 5 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=1e-07 | ok | 15 ms |
| 6 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 14 ms |
| 7 | `get_circuit` | {"circuit_id": "c-7ee828f13d"} | ok | 17 ms |
| 8 | `connect` | pins=[["V1", "-"], ["C1", "2"], ["GND1", "1"]] net=None | ok | 3 ms |
| 9 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=None | ok | 14 ms |
| 10 | `connect` | pins=[["R1", "2"], ["C1", "1"]] net=None | ok | 15 ms |
| 11 | `add_probe` | target=n1 name=out | ok | 10 ms |
| 12 | `add_probe` | target=in name=in | ok | 15 ms |
| 13 | `simulate` | circuit=c-7ee828f13d analysis=transient | ok | 21340 ms |
| 14 | `measure` | sim=s-6f3a22498e probe_id=None what=all | ok | 77 ms |

- 总调用 **14** 次，成功 **13**，失败 **1**
- 连续重复调用（同工具同参数）：**0** 次
- 累计耗时 **21.6 s**（其中 `simulate` 占 21.3 s）
