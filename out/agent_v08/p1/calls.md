| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=rc_lpf_500hz | ok | 4 ms |
| 2 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1.0 parameters={"frequency": 1000} | ok | 14 ms |
| 3 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 17 ms |
| 4 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=3.3e-07 | ok | 16 ms |
| 5 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 16 ms |
| 6 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=in | ok | 18 ms |
| 7 | `connect` | pins=[["R1", "2"], ["C1", "1"]] net=out | ok | 17 ms |
| 8 | `connect` | pins=[["V1", "-"], ["C1", "2"], ["GND1", "1"]] net=None | ok | 17 ms |
| 9 | `add_probe` | target=in name=P_in | ok | 18 ms |
| 10 | `add_probe` | target=out name=P_out | ok | 16 ms |
| 11 | `simulate` | circuit=c-36798c0994 analysis=transient | ok | 20480 ms |
| 12 | `measure` | sim=s-e307dfaa97 probe_id=None what=all | ok | 95 ms |
| 13 | `get_waveform` | sim=s-e307dfaa97 probe_id=None what=None | ok | 4 ms |
| 14 | `simulate` | circuit=c-36798c0994 analysis=transient | ok | 20048 ms |
| 15 | `measure` | sim=s-22aa89a47f probe_id=None what=all | ok | 88 ms |

- 总调用 **15** 次，成功 **15**，失败 **0**
- 连续重复调用（同工具同参数）：**0** 次
- 累计耗时 **40.9 s**（其中 `simulate` 占 20.5 s）
