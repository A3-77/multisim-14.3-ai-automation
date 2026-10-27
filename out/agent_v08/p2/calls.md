| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=rc2_lpf_2k | ok | 4 ms |
| 2 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1.0 parameters={"frequency": 1000} | ok | 15 ms |
| 3 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 15 ms |
| 4 | `add_component` | R2 RESISTOR/RESISTOR_VIRTUAL value=10000 | ok | 14 ms |
| 5 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=4.7e-08 | ok | 19 ms |
| 6 | `add_component` | C2 CAPACITOR/CAPACITOR_VIRTUAL value=4.7e-09 | ok | 19 ms |
| 7 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 14 ms |
| 8 | `connect` | pins=[["V1", "1"], ["R1", "1"]] net=in | ok | 16 ms |
| 9 | `connect` | pins=[["R1", "2"], ["C1", "1"], ["R2", "1"]] net=mid | ok | 16 ms |
| 10 | `connect` | pins=[["R2", "2"], ["C2", "1"]] net=out | ok | 18 ms |
| 11 | `connect` | pins=[["V1", "2"], ["C1", "2"], ["C2", "2"], ["GND1", "1"]] net=0 | ok | 16 ms |
| 12 | `add_probe` | target=out name=P_out | ok | 16 ms |
| 13 | `add_probe` | target=in name=P_in | ok | 17 ms |
| 14 | `simulate` | circuit=c-44ba97b68d analysis=transient | ok | 28764 ms |
| 15 | `measure` | sim=s-29160bf3e9 probe_id=None what=all | ok | 123 ms |
| 16 | `get_waveform` | sim=s-29160bf3e9 probe_id=None what=None | ok | 3 ms |
| 17 | `create_circuit` | name=rc2_lpf_fc2k | ok | 3 ms |
| 18 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1.0 parameters={"frequency": 2000} | ok | 16 ms |
| 19 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 16 ms |
| 20 | `add_component` | R2 RESISTOR/RESISTOR_VIRTUAL value=10000 | ok | 17 ms |
| 21 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=4.7e-08 | ok | 19 ms |
| 22 | `add_component` | C2 CAPACITOR/CAPACITOR_VIRTUAL value=4.7e-09 | ok | 17 ms |
| 23 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 19 ms |
| 24 | `connect` | pins=[["V1", "1"], ["R1", "1"]] net=in | ok | 23 ms |
| 25 | `connect` | pins=[["R1", "2"], ["C1", "1"], ["R2", "1"]] net=mid | ok | 15 ms |
| 26 | `connect` | pins=[["R2", "2"], ["C2", "1"]] net=out | ok | 16 ms |
| 27 | `connect` | pins=[["V1", "2"], ["C1", "2"], ["C2", "2"], ["GND1", "1"]] net=0 | ok | 18 ms |
| 28 | `add_probe` | target=in name=P_in | ok | 17 ms |
| 29 | `add_probe` | target=out name=P_out | ok | 15 ms |
| 30 | `simulate` | circuit=c-0a8adca46f analysis=transient | ok | 26325 ms |
| 31 | `measure` | sim=s-e4b6fab6a2 probe_id=None what=amplitude | ok | 87 ms |

- 总调用 **31** 次，成功 **31**，失败 **0**
- 连续重复调用（同工具同参数）：**0** 次
- 累计耗时 **55.7 s**（其中 `simulate` 占 28.8 s）
