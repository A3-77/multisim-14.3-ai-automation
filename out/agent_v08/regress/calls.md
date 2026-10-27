| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=regress_v080 | ok | 2 ms |
| 2 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1.0 parameters={"frequency": 1000} | ok | 114 ms |
| 3 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 14 ms |
| 4 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=3.3e-08 | ok | 9 ms |
| 5 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 16 ms |
| 6 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=in | ok | 15 ms |
| 7 | `connect` | pins=[["R1", "2"], ["C1", "1"]] net=out | ok | 26 ms |
| 8 | `connect` | pins=[["C1", "2"], ["V1", "-"], ["GND1", "1"]] net=0 | ok | 11 ms |
| 9 | `add_probe` | target=out name=P_out | ok | 12 ms |
| 10 | `add_probe` | target=in name=P_in | ok | 10 ms |
| 11 | `get_circuit` | {"circuit_id": "c-8cb44e993f"} | ok | 13 ms |
| 12 | `simulate` | circuit=c-8cb44e993f analysis=transient | ok | 20991 ms |
| 13 | `measure` | sim=s-55bc7d31b5 probe_id=None what=None | ok | 72 ms |
| 14 | `get_waveform` | sim=s-55bc7d31b5 probe_id=P_out what=None | ok | 3 ms |
| 15 | `measure` | sim=s-55bc7d31b5 probe_id=P_out what=amplitude | ok | 82 ms |

- 总调用 **15** 次，成功 **15**，失败 **0**
- 连续重复调用（同工具同参数）：**0** 次
- 累计耗时 **21.4 s**（其中 `simulate` 占 21.0 s）
