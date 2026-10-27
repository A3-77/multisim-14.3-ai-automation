| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=rc_lowpass_1k_100n | ok | 2 ms |
| 2 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 parameters={"frequency": 1000} | ok | 13 ms |
| 3 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 16 ms |
| 4 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=1e-07 | ok | 13 ms |
| 5 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 12 ms |
| 6 | `connect` | pins=[["V1", "2"], ["GND1", "1"], ["C1", "2"]] net=None | ok | 12 ms |
| 7 | `connect` | pins=[["V1", "1"], ["R1", "1"]] net=None | ok | 12 ms |
| 8 | `connect` | pins=[["R1", "2"], ["C1", "1"]] net=out | ok | 13 ms |
| 9 | `add_probe` | target=out name=P1 | ok | 13 ms |
| 10 | `add_probe` | target=in name=P2 | ok | 12 ms |
| 11 | `simulate` | circuit=c-0a8bdb9b95 analysis=transient | ok | 19476 ms |
| 12 | `get_waveform` | sim=s-820fdadf29 probe_id=V(探针1) what=None | **PROBE_NOT_FOUND** | 16 ms |
| 13 | `get_waveform` | sim=s-820fdadf29 probe_id=P1 what=None | ok | 3 ms |
| 14 | `measure` | sim=s-820fdadf29 probe_id=None what=all | ok | 57 ms |
| 15 | `simulate` | circuit=c-0a8bdb9b95 analysis=transient | ok | 20102 ms |
| 16 | `measure` | sim=s-7116e2f2de probe_id=None what=all | ok | 71 ms |

- 总调用 **16** 次，成功 **15**，失败 **1**
- 连续重复调用（同工具同参数）：**0** 次
- 累计耗时 **39.8 s**（其中 `simulate` 占 20.1 s）
