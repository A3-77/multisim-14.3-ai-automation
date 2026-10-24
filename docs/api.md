# Multisim Automation API 参考

从 `MSInterface.dll` 的类型库直接导出，未做人工增删。
ProgID：`MultisimInterface.MultisimApp` / `MultisimInterface.MultisimCircuit`。
官方文档：https://www.ni.com/docs/zh-CN/bundle/multisim/page/topics/enumoutputs.html

## 应用对象 IMultisimApp

| 成员 | 参数 | 说明 |
| --- | --- | --- |
| `Connect` | — | Connect to a new instance of Multisim |
| `get_Path`（只读属性） | pVal: str  ← 输出 | Full path to Multisim executable |
| `set_Path`（只写属性） | pVal: str | Full path to Multisim executable |
| `get_IsConnected`（只读属性） | pVal: bool  ← 输出 | Returns true if connected to an active instance of Multisim |
| `get_LastErrorMessage`（只读属性） | pVal: str  ← 输出 | Last error message caused in this instance of Multisim |
| `get_VersionInfo`（只读属性） | pVal: str  ← 输出 | Full name and version of this instance of Multisim |
| `OpenFile` | FileName: str; newMultisimCircuit: IMultisimCircuit  ← 输出 | Open an existing Multisim circuit file |
| `Disconnect` | — | Shut down and disconnect from this instance of Multisim |
| `NewFile` | newMultisimCircuit: IMultisimCircuit  ← 输出 | Create a new blank Multisim circuit file |
| `get_LogFile`（只读属性） | pVal: str  ← 输出 | Full path to Multisim log file |
| `set_LogFile`（只写属性） | pVal: str | Full path to Multisim log file |

## 电路对象 IMultisimCircuit

| 成员 | 参数 | 说明 |
| --- | --- | --- |
| `get_CircuitName`（只读属性） | pVal: str  ← 输出 | Name of top-level circuit |
| `get_FileName`（只读属性） | pVal: str  ← 输出 | Circuit file name including full path |
| `get_LastErrorMessage`（只读属性） | pVal: str  ← 输出 | Last error message caused in this instance of Multisim |
| `get_SimulationState`（只读属性） | pVal: int  ← 输出 | Current state of the simulator |
| `RunSimulation` | numSeconds: float; pause: bool | Run the simulation for a given amount of time |
| `RunSimulationUntilNextOutput` | — | Run the simulation until the next output is ready |
| `StopSimulation` | — | Stop the simulation |
| `PauseSimulation` | — | Pause the simulation |
| `ResumeSimulation` | — | Resume a paused simulation |
| `EnumOutputs` | outputType: int; outputNames: variant  ← 输出 | Get a list of available outputs |
| `SetOutputRequest` | outputName: str; method: int; sampleRate: float; numSamples: int; repeatFlag: bool | Set a request for output data |
| `get_OutputReady`（只读属性） | outputName: str; pVal: bool  ← 输出 | Does this output have data ready to retrieve |
| `GetOutputData` | outputName: str; dataArray: variant  ← 输出; method: int  ← 输出 | Get the data accumulated at an output |
| `ClearOutputRequest` | outputName: str | Clear a request for output data |
| `EnumInputs` | inputType: int; inputNames: variant  ← 输出 | Get a list of available inputs |
| `SetInputDataRaw` | inputName: str; dataArray: variant; bRepeat: bool | Set X-Y input data |
| `SetInputDataSampled` | inputName: str; sampleRate: float; dataArray: variant; bRepeat: bool | Set sampled input data |
| `ReserveInput` | inputName: str | Reserve an input for data later in the simulation |
| `ClearInputData` | inputName: str | Clear an input data request |
| `WaitForNextOutput` | bTimedOut: bool  ← 输出; nWaitTime: int; outputNames: variant  ← 输出 | Wait until the simulation has output data ready |
| `DoCommandLine` | commandFileName: str; logFileName: str | Execute a set of XSPICE commands |
| `DoACSweep` | SweepType: int; numPoints: int; startFrequency: float; stopFrequency: float; outputNames: variant | Do an AC analysis |
| `get_ActiveVariant`（只读属性） | pVal: str  ← 输出 | The active variant of the circuit |
| `set_ActiveVariant`（只写属性） | pVal: str | The active variant of the circuit |
| `EnumVariants` | variantNames: variant  ← 输出 | Enumerate available variants in opened circuit |
| `ReportBOM` | realFlag: bool; format: int; FileName: variant; outputBOM: str  ← 输出 | Generate a Bill of Materials Report |
| `ReportNetlist` | probesFlag: bool; format: int; FileName: variant; outputNetlist: str  ← 输出 | Generate a Netlist Report |
| `EnumComponents` | filterType: int; components: variant  ← 输出 | Enumerate the components in a circuit |
| `get_RLCValue`（只读属性） | componentName: str; pVal: float  ← 输出 | The value of an RLC component |
| `set_RLCValue`（只写属性） | componentName: str; pVal: float | The value of an RLC component |
| `ReplaceComponent` | componentName: str; sectionName: str; sourceDatabase: int; sourceGroup: str; sourceFamily: str; sourceName: str; modelName: str; newComponentName: str  ← 输出 | Replace a component in the circuit with another component |
| `GetCircuitImage` | imageFormat: int; FileName: str; savedFile: str  ← 输出 | Save a snapshot of the circuit to a file |
| `Save` | savedFile: str  ← 输出 | Save the open circuit |
| `SaveAs` | FileName: str; savedFile: str  ← 输出 | Save the open circuit to a specific location |
| `EnumSections` | componentName: str; sections: variant  ← 输出 | Enumerate all available sections for a given component. |
| `SaveDesignAsSnippet` | FileName: str; zoomFactor: float; savedFile: str  ← 输出 | Save a design snippet for the current open design |
| `CreateSnippet` | FileName: str; selectionOnlyFlag: bool; zoomFactor: float; savedFile: str  ← 输出 | Create a snippet from the content of the current active circuit |
| `EnumCircuitParameters` | uLevel: int; circuitparameters: variant  ← 输出 | Enumerate the circuit parameters in the design |
| `get_CircuitParameterValue`（只读属性） | strName: str; pVal: float  ← 输出 | Get value of a circuit parameter |
| `set_CircuitParameterValue`（只写属性） | strName: str; pVal: float | Get value of a circuit parameter |
| `DoDCOperatingPoint` | outputNames: variant | Do a DC operating point analysis |
| `DoACSingleFrequency` | frequency: float; outputNames: variant | Do an AC single frequency analysis |

## 枚举

- **SimulationState**：SimulationStopped=0、SimulationRunning=1、SimulationPaused=2
- **SimulationIOType**：SimulationIOAll=0、SimulationIOVoltage=1、SimulationIOCurrent=2、SimulationIOPower=3、SimulationIODigital=4
- **SimulationInterpolation**：SimulationInterpolationRaw=0、SimulationInterpolationForceStep=1、SimulationInterpolationLinear=2、SimulationInterpolationSpline=3、SimulationInterpolationCoerce=4
- **SweepType**：SweepDecade=0、SweepOctave=1、SweepLinear=2
- **ComponentType**：ComponentAll=0、ComponentAllRLC=1、ComponentResistor=2、ComponentCapacitor=3、ComponentInductor=4
- **CircuitParameterLevel**：AllCircuitParameters=0、TopLevelCircuitParameters=1
- **ExportFormat**：ExportText=0、ExportCSV=1
- **CircuitImageFormat**：CircuitImagePNG=0、CircuitImageJPG=1、CircuitImageBMP=2