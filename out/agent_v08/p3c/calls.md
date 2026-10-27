| # | 工具 | 关键参数 | 结果 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `create_circuit` | name=rc_lowpass_p3c | ok | 4 ms |
| 2 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 | ok | 16 ms |
| 3 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 17 ms |
| 4 | `add_component` | R2 RESISTOR/RESISTOR_VIRTUAL value=10000 | ok | 12 ms |
| 5 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=1e-08 | ok | 9 ms |
| 6 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 16 ms |
| 7 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=in | ok | 9 ms |
| 8 | `connect` | pins=[["R1", "2"], ["R2", "1"], ["C1", "1"]] net=out | ok | 14 ms |
| 9 | `connect` | pins=[["V1", "-"], ["R2", "2"], ["C1", "2"], ["GND1", "1"]] net=0 | ok | 10 ms |
| 10 | `add_probe` | target=in name=P_in | ok | 13 ms |
| 11 | `add_probe` | target=out name=P_out | ok | 14 ms |
| 12 | `get_circuit` | {"circuit_id": "c-65aef7c37f"} | ok | 11 ms |
| 13 | `simulate` | circuit=c-65aef7c37f analysis=transient | **LAYOUT_UNSUPPORTED** | 1 ms |
| 14 | `create_circuit` | name=altA_divider_1k_10k | ok | 2 ms |
| 15 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 | ok | 16 ms |
| 16 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 14 ms |
| 17 | `add_component` | R2 RESISTOR/RESISTOR_VIRTUAL value=10000 | ok | 13 ms |
| 18 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 11 ms |
| 19 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=in | ok | 8 ms |
| 20 | `connect` | pins=[["R1", "2"], ["R2", "1"]] net=out | ok | 12 ms |
| 21 | `connect` | pins=[["V1", "-"], ["R2", "2"], ["GND1", "1"]] net=0 | ok | 8 ms |
| 22 | `add_probe` | target=in name=P_in | ok | 9 ms |
| 23 | `add_probe` | target=out name=P_out | ok | 14 ms |
| 24 | `get_circuit` | {"circuit_id": "c-81c5564135"} | ok | 7 ms |
| 25 | `get_circuit` | {"circuit_id": "c-81c5564135"} | ok | 1 ms |
| 26 | `simulate` | circuit=c-81c5564135 analysis=transient | ok | 21869 ms |
| 27 | `measure` | sim=s-6896ec784a probe_id=None what=all | ok | 69 ms |
| 28 | `create_circuit` | name=altB_rc_1k_10n | ok | 3 ms |
| 29 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 | ok | 13 ms |
| 30 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=1000 | ok | 11 ms |
| 31 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=1e-08 | ok | 11 ms |
| 32 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 8 ms |
| 33 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=in | ok | 10 ms |
| 34 | `connect` | pins=[["R1", "2"], ["C1", "1"]] net=out | ok | 11 ms |
| 35 | `connect` | pins=[["V1", "-"], ["C1", "2"], ["GND1", "1"]] net=0 | ok | 8 ms |
| 36 | `add_probe` | target=in name=P_in | ok | 9 ms |
| 37 | `add_probe` | target=out name=P_out | ok | 11 ms |
| 38 | `get_circuit` | {"circuit_id": "c-de0d8b09ea"} | ok | 8 ms |
| 39 | `simulate` | circuit=c-de0d8b09ea analysis=transient | ok | 19005 ms |
| 40 | `measure` | sim=s-d8a9c65ccd probe_id=None what=all | ok | 72 ms |
| 41 | `create_circuit` | name=altC_pole_req_909 | ok | 2 ms |
| 42 | `add_component` | V1 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE value=1 | ok | 13 ms |
| 43 | `add_component` | R1 RESISTOR/RESISTOR_VIRTUAL value=909.0909090909091 | ok | 12 ms |
| 44 | `add_component` | C1 CAPACITOR/CAPACITOR_VIRTUAL value=1e-08 | ok | 8 ms |
| 45 | `add_component` | GND1 POWER_SOURCES/GROUND value=None | ok | 12 ms |
| 46 | `connect` | pins=[["V1", "+"], ["R1", "1"]] net=in | ok | 8 ms |
| 47 | `connect` | pins=[["R1", "2"], ["C1", "1"]] net=out | ok | 13 ms |
| 48 | `connect` | pins=[["V1", "-"], ["C1", "2"], ["GND1", "1"]] net=0 | ok | 8 ms |
| 49 | `add_probe` | target=in name=P_in | ok | 8 ms |
| 50 | `add_probe` | target=out name=P_out | ok | 14 ms |
| 51 | `simulate` | circuit=c-c0b755640f analysis=transient | ok | 19498 ms |
| 52 | `measure` | sim=s-9919e2ef63 probe_id=None what=all | ok | 72 ms |

- 总调用 **52** 次，成功 **51**，失败 **1**
- 连续重复调用（同工具同参数）：**1** 次
- 累计耗时 **61.0 s**（其中 `simulate` 占 21.9 s）
