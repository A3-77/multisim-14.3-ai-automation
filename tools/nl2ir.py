# -*- coding: utf-8 -*-
"""中文自然语言 -> Circuit IR（确定性规则解析器）。

为什么是规则，不是 LLM
----------------------
这一层要做的是"可验证"。同一句话必须永远解析成同一份 IR，否则下游的
.ms14 和仿真结果就不可复现。规则解析器能做到这一点，而且解析失败时能
精确指出"缺哪个字段"。

LLM 的位置在更上层：把自由表述规范化成受控句式，再交给这里。本模块
不依赖任何网络/模型，纯标准库。

三条硬规则
----------
1. **只产出 IR**。不碰 XML、不碰 .ms14、不碰 Multisim。
2. **产出前先校验**。解析完立刻 `CircuitIR.validate()`，错误在写盘之前抛出。
3. **不猜**。缺频率、缺阻值、拓扑不支持 —— 一律报错并说清缺什么。
   猜错一个值，仿真结果看起来"能跑"，但结论是错的，这比报错危险得多。

支持的句式（正向用例见 tools/test_nl2ir.py）
--------------------------------------------
元件（值在前或在后都行）
    "1kΩ 电阻" / "电阻 1kΩ" / "电阻 R1 = 1kΩ" / "R1 为 1kΩ"
    "159nF 电容" / "电容 159nF" / "C1 是 159nF"
    "1V、1kHz 正弦源" / "1V 1kHz 交流电压源" / "5V 直流电源"（直流会明确报不支持）
    "接地" / "到地" / "GND"

拓扑（串联链）
    "串联"、"经过 ... 后接 ..."、"再接到 ..."、"到地"
    "并联" → 明确报"暂不支持并联"
    顺序 = 元件在句子里的出现顺序，最后统一接地

探针
    "在输出节点放一个电压探针"
    "在输入节点和输出节点各放一个电压探针"（一句话两个探针）
    "在 R1 两端放电压探针" / "在电阻两端各放一个电压探针"（两端 = 两个网络各一个）

仿真
    "做瞬态分析"（默认）、"仿真 6ms"、"仿真 6 个周期"、"采样率 200kHz"
    没写时长 → 6 个信号周期；没写采样率 → 200 × 信号频率
    "交流分析 / 扫频 / 直流工作点" → 明确报"暂不支持"

用法
----
    import nl2ir
    ir, rep = nl2ir.parse("1V 1kHz 正弦源，经过 1kΩ 电阻后接 159nF 电容到地，"
                          "在输入和输出各放一个电压探针，做瞬态分析")
    print(ir.summary())
    ir.save("out/nl/rc.ir.json")

命令行：
    python tools/nl2ir.py "一句话描述" -o out/nl/x.ir.json
    python tools/nl2ir.py --file examples/nl/rc_lowpass.txt
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import circuit_ir as irmod  # noqa: E402

IR_VERSION = irmod.IR_VERSION


class NLParseError(Exception):
    """解析失败。issues 里是给人和给 LLM 看的具体原因，一条一行。"""

    def __init__(self, issues, text=None):
        self.issues = list(issues)
        self.text = text
        super().__init__("；".join(self.issues))


# ---------------------------------------------------------------- 归一化

_FULLWIDTH = str.maketrans({
    "，": ",", "。": ".", "；": ";", "：": ":", "（": "(", "）": ")",
    "％": "%", "　": " ", "＝": "=", "－": "-", "＋": "+", "／": "/",
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9", "．": ".",
})

# 中文单位 -> 符号。**长的必须排在前面**（"千欧" 要先于 "欧"）。
_UNIT_ALIAS = (
    ("千欧姆", "kΩ"), ("兆欧姆", "MΩ"), ("千欧", "kΩ"), ("兆欧", "MΩ"),
    ("欧姆", "Ω"), ("欧", "Ω"),
    ("纳法", "nF"), ("微法", "uF"), ("皮法", "pF"), ("毫法", "mF"),
    ("法拉", "F"),
    ("千伏", "kV"), ("毫伏", "mV"), ("微伏", "uV"), ("伏特", "V"), ("伏", "V"),
    ("千赫兹", "kHz"), ("兆赫兹", "MHz"), ("千赫", "kHz"), ("兆赫", "MHz"),
    ("赫兹", "Hz"), ("赫", "Hz"),
    ("毫秒", "ms"), ("微秒", "us"), ("纳秒", "ns"), ("秒钟", "s"),
    ("μ", "u"), ("µ", "u"),
    ("KHz", "kHz"), ("KHZ", "kHz"), ("khz", "kHz"),
    ("MHZ", "MHz"), ("mhz", "MHz"), ("HZ", "Hz"), ("hz", "Hz"),
    ("UF", "uF"), ("NF", "nF"), ("PF", "pF"),
    ("OHM", "Ω"), ("ohm", "Ω"),
)


def normalize(text):
    t = str(text).translate(_FULLWIDTH)
    for a, b in _UNIT_ALIAS:
        t = t.replace(a, b)
    return t


# ---------------------------------------------------------------- 词表

_UNITS = {
    # 单位: (量纲, 倍率)
    "Ω": ("res", 1.0), "kΩ": ("res", 1e3), "MΩ": ("res", 1e6), "mΩ": ("res", 1e-3),
    "F": ("cap", 1.0), "mF": ("cap", 1e-3), "uF": ("cap", 1e-6),
    "nF": ("cap", 1e-9), "pF": ("cap", 1e-12),
    "V": ("volt", 1.0), "mV": ("volt", 1e-3), "uV": ("volt", 1e-6), "kV": ("volt", 1e3),
    "Hz": ("freq", 1.0), "kHz": ("freq", 1e3), "MHz": ("freq", 1e6),
    "s": ("time", 1.0), "ms": ("time", 1e-3), "us": ("time", 1e-6), "ns": ("time", 1e-9),
}

_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))

# 数值 + 单位。前后不允许紧贴字母数字，避免把 "R1" / "V2" 当成数值。
_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)\s*(%s)(?![A-Za-z0-9])" % _UNIT_ALT)

# 元件类型词。同一起点上取最长匹配（"正弦电压源" 优先于 "电压源"）。
_TYPE_PATTERNS = (
    ("source", re.compile(r"正弦波?电压源|正弦电压源|正弦信号源|正弦波?源|正弦源|"
                          r"交流电压源|交流信号源|交流电源|交流源|信号源|电压源|"
                          r"直流电压源|直流电源|直流源|电源")),
    ("resistor", re.compile(r"电阻器|电阻")),
    ("capacitor", re.compile(r"电容器|电容")),
    ("inductor", re.compile(r"电感器|电感|线圈")),
    ("unsupported", re.compile(r"二极管|三极管|晶体管|运算放大器|运放|稳压管|"
                               r"场效应管|MOS|变压器|开关|继电器|芯片")),
)

_REFDES_RE = re.compile(r"(?<![A-Za-z0-9])([RCV])(\d{1,3})(?![0-9])")
_REFDES_KIND = {"R": "resistor", "C": "capacitor", "V": "source"}

_GROUND_RE = re.compile(r"接地|到地|接到地|连到地|地线|公共端|GND")

_SIM_TRANSIENT = re.compile(r"瞬态|时域|transient", re.I)
_SIM_UNSUPPORTED = (
    (re.compile(r"交流分析|AC\s*分析|频率响应|扫频|幅频|相频|波特", re.I), "交流/扫频分析"),
    (re.compile(r"直流工作点|静态工作点|DC\s*分析|工作点分析", re.I), "直流工作点分析"),
    (re.compile(r"蒙特卡洛|温度扫描|参数扫描|噪声分析|失真分析"), "高级分析"),
)
_STOP_TIME_RE = re.compile(r"仿真\s*(?:时间|时长|窗口)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(%s)"
                           % _UNIT_ALT)
_PERIOD_RE = re.compile(r"(\d+)\s*个?\s*周期")
_SR_RE = re.compile(r"采样率\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(kHz|Hz)", re.I)

_PROBE_RE = re.compile(
    r"(?:在|于)\s*([^,;。]{0,26}?)\s*(?:各)?\s*"
    r"(?:放|放置|加|添加|接|布)\s*(?:置|上)?\s*"
    r"(?:一个|1个|两个|2个|各一个|各1个)?\s*(?:电压)?\s*探针")

_MODIFY_RE = re.compile(r"改成|改为|修改|删掉|删除|去掉|把.*换|替换")

# 布局：与 tools/build_rc_lowpass.py 里实测通过的那组坐标一致。
# 坐标含义是**引脚质心**（add_part 的 anchor="pin"）。
_LAYOUT_SRC = (300.0, 300.0)
_LAYOUT_GND = (300.0, 420.0)
_LAYOUT_PASSIVE = ((500.0, 300.0), (700.0, 400.0))

MAX_PASSIVES = 2     # 只验证过 1~2 个无源元件的串联链布局


# ---------------------------------------------------------------- 小工具

def _mask(text, spans):
    """把已经消费掉的片段替换成等长空格，保持字符位置不变。"""
    if not spans:
        return text
    buf = list(text)
    for s, e in spans:
        for i in range(max(0, s), min(len(buf), e)):
            buf[i] = " "
    return "".join(buf)


def _span_dist(a0, a1, b0, b1):
    """两段区间的字符距离（重叠为 0）。"""
    if a1 <= b0:
        return b0 - a1
    if b1 <= a0:
        return a0 - b1
    return 0


def _scan_types(text):
    """返回 [(start, end, kind, word)]，同起点取最长匹配。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        best = None
        for kind, pat in _TYPE_PATTERNS:
            m = pat.match(text, i)
            if m and (best is None or m.end() > best[1].end()):
                best = (kind, m)
        if best:
            kind, m = best
            out.append((m.start(), m.end(), kind, m.group(0)))
            i = m.end()
        else:
            i += 1
    return out


def _scan_tokens(text):
    """返回 [(start, end, value, dim, unit, 原样文本)]。"""
    out = []
    for m in _TOKEN_RE.finditer(text):
        dim, scale = _UNITS[m.group(2)]
        out.append((m.start(), m.end(), float(m.group(1)) * scale, dim,
                    m.group(2), m.group(0)))
    return out


# 数值和类型词之间允许出现的东西：空格 / 顿号 / 逗号 / 等号 / "的" / 参数标签 / 位号。
# 出现别的字（尤其是"接、连、串、经、和"这类连接词）就认为已经跨到另一个元件了。
_GAP_OK = re.compile(r"^[\s、,，=:为是的]*(?:频率|幅值|阻值|容值|电压|值|[RCV]\d{1,3})?"
                     r"[\s、,，=:为是的]*$")
_GAP_BREAK = re.compile(r"接|连|串|经|到|后|再|并|和|与|及|各")


def _gap_ok(gap, allow_dun):
    """数值与类型词之间的间隔是否"还属于同一个短语"。"""
    if not gap:
        return True
    if not allow_dun and "、" in gap:
        return False
    if _scan_types(gap):
        return False
    if _GAP_BREAK.search(gap):
        return False
    return bool(_GAP_OK.match(gap))


def _collect_values(text, toks, ts, te):
    """把紧贴类型词的数值都收进来（值在前、值在后两种语序都支持）。

    规则是"连续的一段"，不是"最近的几个"：
        "1V、1kHz 正弦源"     -> 两个都收
        "1kΩ 电阻后接 159nF 电容" -> 电阻只收 1kΩ（"后接"是分界）
    这样两个同类元件并列时不会互相抢数值。
    """
    before = []
    cur = ts
    for j in range(len(toks) - 1, -1, -1):
        s, e = toks[j][0], toks[j][1]
        if e > cur:
            continue
        if not _gap_ok(text[e:cur], allow_dun=True):
            break
        before.append(j)
        cur = s
    before.reverse()

    after = []
    cur = te
    for j in range(len(toks)):
        s, e = toks[j][0], toks[j][1]
        if s < cur:
            continue
        if not _gap_ok(text[cur:s], allow_dun=False):
            break
        after.append(j)
        cur = e
    return before + after


def _fmt_value(v):
    """给解释文字用的数值格式（1e-09 这种不好读）。"""
    if v is None:
        return "?"
    if abs(v) >= 1e6 or (0 < abs(v) < 1e-6):
        return "%.4g" % v
    return ("%.6g" % v)


# ---------------------------------------------------------------- 解析主体

def parse(text, name=None, strict=True):
    """中文描述 -> (CircuitIR, 解析报告 dict)。

    失败抛 NLParseError，issues 里是具体原因。
    strict=False 时，validate() 的错误也当成报告返回（给测试/调试用）。
    """
    if not text or not str(text).strip():
        raise NLParseError(["描述为空"], text)

    raw = str(text)
    t = normalize(raw)
    issues = []
    notes = []          # 解析过程中的取舍，最后打印给人看
    spans = []          # 已消费片段，最后统一 mask

    # ---------- 0) 明确拒绝"修改已有电路" ----------
    if _MODIFY_RE.search(t) and not re.search(r"新建|创建|画|生成|搭建|做一个", t):
        raise NLParseError([
            "这句话像是在修改已有电路（%r）。本层只支持从零新建电路；"
            "修改已有 .ms14 请直接操作 Circuit 对象。" % _MODIFY_RE.search(t).group(0)
        ], raw)

    # ---------- 1) 仿真块 ----------
    sim = {"analysis": "transient", "start": 0.0, "stop": None,
           "step": None, "sample_rate": None}

    m = _SIM_UNSUPPORTED[0][0].search(t)
    if m:
        raise NLParseError([
            "只支持瞬态分析（transient）。检测到 %r —— %s 暂未接入 IR，"
            "因为 COM 侧取数路径还没验证过。" % (m.group(0), "交流/扫频分析")
        ], raw)
    for pat, label in _SIM_UNSUPPORTED[1:]:
        m = pat.search(t)
        if m:
            raise NLParseError([
                "只支持瞬态分析（transient）。检测到 %r —— %s 暂未接入 IR。"
                % (m.group(0), label)
            ], raw)
    if _SIM_TRANSIENT.search(t):
        notes.append("分析类型：瞬态（transient）")

    m = _SR_RE.search(t)
    if m:
        val = float(m.group(1)) * (1e3 if m.group(2).lower() == "khz" else 1.0)
        sim["sample_rate"] = val
        spans.append(m.span())
        notes.append("采样率：%s Hz（来自描述）" % _fmt_value(val))

    m = _STOP_TIME_RE.search(t)
    if m:
        val = float(m.group(1)) * _UNITS[m.group(2)][1]
        sim["stop"] = val
        spans.append(m.span())
        notes.append("仿真时长：%s s（来自描述）" % _fmt_value(val))

    period_m = _PERIOD_RE.search(t)
    if period_m:
        spans.append(period_m.span())
        notes.append("仿真时长：%s 个信号周期（来自描述）" % period_m.group(1))

    # ---------- 2) 探针短语（先摘出来，再 mask，避免"在电阻两端"被当成新元件） ----------
    probe_phrases = []
    for m in _PROBE_RE.finditer(t):
        probe_phrases.append((m.start(), m.end(), m.group(1).strip()))
        spans.append(m.span())
    if probe_phrases:
        notes.append("探针描述：%s"
                     % " / ".join("「%s」" % p[2] for p in probe_phrases))

    t_masked = _mask(t, spans)

    # ---------- 3) 元件 ----------
    types = _scan_types(t_masked)
    tokens = _scan_tokens(t_masked)

    if not types:
        raise NLParseError([
            "没识别出任何元件。可用的词：电阻 / 电容 / 正弦源（电源）/ 地。"
            "例：'1V 1kHz 正弦源，经过 1kΩ 电阻后接 159nF 电容到地'"
        ], raw)

    # 不支持的元件先报，别让它走后面那套赋值逻辑
    bad = [(s, e, k, w) for (s, e, k, w) in types if k in ("inductor", "unsupported")]
    if bad:
        raise NLParseError([
            "元件 %r 不在已验证白名单里。Circuit IR 目前只接受：%s。"
            "（白名单的每一项都在 Multisim 里跑通过仿真，没验证过的不加）"
            % (w, "、".join("%s/%s" % k for k in irmod.SUPPORTED))
            for (_s, _e, _k, w) in bad
        ], raw)

    # 数值 -> 类型词：按"连续短语"归属，不按"最近距离"抢
    comp_types = [(s, e, k, w) for (s, e, k, w) in types
                  if k in ("source", "resistor", "capacitor")]
    comp_types.sort()
    value_toks = [t for t in tokens if t[3] != "time"]
    want_dims = {"source": ("volt", "freq"), "resistor": ("res",), "capacitor": ("cap",)}
    assigned = {}
    used_tok = set()
    for i, (ts, te, kind, _word) in enumerate(comp_types):
        mine = []
        for j in _collect_values(t_masked, value_toks, ts, te):
            tok = value_toks[j]
            if tok[3] in want_dims[kind]:
                used_tok.add(j)
                mine.append(tok)
        assigned[i] = mine
    orphan = [value_toks[j][5] for j in range(len(value_toks)) if j not in used_tok]

    if orphan:
        issues.append("这些数值找不到对应的元件：%s（单位量纲不匹配任何已识别的元件）"
                      % "、".join(orphan))

    # 位号：按字母就近挂到同类元件上
    refdes_pool = {}
    for m in _REFDES_RE.finditer(t_masked):
        refdes_pool.setdefault(m.group(0), []).append((m.start(), m.end(),
                                                       _REFDES_KIND[m.group(1)]))
    used_refdes = set()

    comps = []          # [(kind, refdes, value, params, position)]
    source = None
    passives = []

    for i, (ts, te, kind, word) in enumerate(comp_types):
        mine = assigned[i]
        # 位号
        refdes = None
        cand = []
        for rd, occ in refdes_pool.items():
            for (s, e, k) in occ:
                if k == kind:
                    cand.append((_span_dist(ts, te, s, e), s, rd))
        cand = [c for c in cand if c[2] not in used_refdes]
        if cand:
            cand.sort()
            # 只在"紧挨着"的时候采纳（避免把远处另一个 R2 的位号抢过来）
            if cand[0][0] <= 8:
                refdes = cand[0][2]
                used_refdes.add(refdes)

        if kind == "source":
            if source is not None:
                issues.append("识别到多个电源（%s 和 %r），IR 目前只支持单一电源"
                              % (source["refdes"], word))
                continue
            volt = [x for x in mine if x[3] == "volt"]
            freq = [x for x in mine if x[3] == "freq"]
            if not volt:
                issues.append("电源 %r 没给幅值（例：'1V 1kHz 正弦源'）" % word)
                continue
            if len(volt) > 1:
                issues.append("电源 %r 给了多个幅值：%s"
                              % (word, "、".join(v[5] for v in volt)))
                continue
            is_dc = ("直流" in word) or (not freq and not re.search(r"正弦|交流|信号", word))
            if is_dc:
                issues.append(
                    "电源 %r 看着是直流源。直流源（POWER_SOURCES/DC_POWER）"
                    "不在已验证白名单里 —— 当前只有 SIGNAL_VOLTAGE_SOURCES/AC_VOLTAGE。"
                    "请给正弦源：'1V 1kHz 正弦源'。" % word)
                continue
            if not freq:
                issues.append("正弦源 %r 没给频率（例：'1V 1kHz 正弦源'）" % word)
                continue
            if len(freq) > 1:
                issues.append("正弦源 %r 给了多个频率：%s"
                              % (word, "、".join(f[5] for f in freq)))
                continue
            source = {
                "refdes": refdes or "V1", "family": "SIGNAL_VOLTAGE_SOURCES",
                "part": "AC_VOLTAGE", "value": volt[0][2],
                "params": {5: freq[0][2]}, "amp": volt[0][2], "freq": freq[0][2],
            }
            continue

        # 无源元件
        want_dim = "res" if kind == "resistor" else "cap"
        vals = [x for x in mine if x[3] == want_dim]
        label = "阻值" if kind == "resistor" else "容值"
        if not vals:
            issues.append("%s %r 没给%s（例：'%s'）"
                          % ("电阻" if kind == "resistor" else "电容", word, label,
                             "1kΩ 电阻" if kind == "resistor" else "159nF 电容"))
            continue
        if len(vals) > 1:
            issues.append("%s %r 给了多个%s：%s"
                          % ("电阻" if kind == "resistor" else "电容", word, label,
                             "、".join(v[5] for v in vals)))
            continue
        passives.append({
            "refdes": refdes or ("R%d" if kind == "resistor" else "C%d")
            % (sum(1 for p in passives if p["family"] == ("RESISTOR" if kind == "resistor"
                                                          else "CAPACITOR")) + 1),
            "family": "RESISTOR" if kind == "resistor" else "CAPACITOR",
            "part": "RESISTOR_VIRTUAL" if kind == "resistor" else "CAPACITOR_VIRTUAL",
            "value": vals[0][2],
        })

    # ---------- 4) 拓扑 ----------
    if "并联" in t:
        issues.append("检测到'并联'：IR 目前只支持'串联链 + 接地'这一种拓扑。"
                      "并联电路还没验证过布局，请改成分立串联描述。")

    if source is None and not issues:
        issues.append("没找到信号源。IR 需要恰好一个正弦源，例：'1V 1kHz 正弦源'")
    if not passives and not issues:
        issues.append("没找到无源元件。至少需要一个电阻或电容。")
    if len(passives) > MAX_PASSIVES:
        issues.append("串联链里有 %d 个无源元件，超过已验证上限 %d 个"
                      "（布局只实测过 1~2 个，多出来的元件位置没验证过）。"
                      % (len(passives), MAX_PASSIVES))
    has_gnd = bool(_GROUND_RE.search(t))
    if not has_gnd and not issues:
        issues.append("没找到地。串联链必须回到地，请加'到地'或'接地'。")

    if issues:
        raise NLParseError(issues, raw)

    # ---------- 5) 网络 ----------
    chain = [source] + passives
    nets = []
    prev = "%s.+" % source["refdes"]
    for i, comp in enumerate(passives):
        nets.append({"name": None, "pins": [prev, "%s.1" % comp["refdes"]]})
        prev = "%s.2" % comp["refdes"]
    nets.append({"name": "0", "pins": ["%s.-" % source["refdes"], "GND1.1", prev]})

    # 命名：首网 in，末网 0，最后一个无源元件之前的那个网叫 out，其余 n1/n2
    nets[0]["name"] = "in"
    if len(nets) >= 3:
        nets[-2]["name"] = "out"
    k = 0
    for n in nets:
        if n["name"] is None:
            k += 1
            n["name"] = "n%d" % k

    # ---------- 6) 探针 ----------
    probes = []
    pidx = [0]

    def add_probe(net_name):
        if net_name not in [n["name"] for n in nets]:
            issues.append("探针目标网络 %r 不存在（现有网络：%s）"
                          % (net_name, ", ".join(n["name"] for n in nets)))
            return
        pidx[0] += 1
        probes.append({"refdes": "P%d" % pidx[0], "kind": "V", "net": net_name})

    def nets_of(refdes):
        """某个元件的两个网络（先入后出）。"""
        if refdes == source["refdes"]:
            return [nets[0]["name"], nets[-1]["name"]]
        for i, comp in enumerate(passives):
            if comp["refdes"] == refdes:
                return [nets[i]["name"], nets[i + 1]["name"]]
        return []

    for (_s, _e, phrase) in probe_phrases:
        parts = [p for p in re.split(r"和|与|、|,|\+", phrase) if p.strip()]
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "两端" in part or "两侧" in part:
                head = re.split(r"两端|两侧", part)[0].strip()
                rd = None
                m = re.search(r"[RCV]\d{1,3}", head)
                if m:
                    rd = m.group(0)
                else:
                    if re.search(r"电阻", head):
                        cand = [p["refdes"] for p in passives if p["family"] == "RESISTOR"]
                    elif re.search(r"电容", head):
                        cand = [p["refdes"] for p in passives if p["family"] == "CAPACITOR"]
                    elif re.search(r"源|电源", head):
                        cand = [source["refdes"]]
                    else:
                        cand = []
                    if len(cand) == 1:
                        rd = cand[0]
                    elif len(cand) > 1:
                        issues.append("'%s' 指的是哪个元件不明确（候选：%s），请写位号"
                                      % (part, "、".join(cand)))
                        continue
                if rd is None:
                    issues.append("看不懂探针位置「%s」：'两端'前面没有能识别的元件" % part)
                    continue
                for nm in nets_of(rd):
                    add_probe(nm)
                continue
            if re.search(r"输出|out|Vout", part, re.I):
                if len(passives) < 2:
                    issues.append("要输出节点至少需要两个无源元件（输出取在最后一个"
                                  "元件之前）。只有一个元件时请说'在 %s 两端'。"
                                  % passives[0]["refdes"])
                else:
                    add_probe("out")
                continue
            if re.search(r"输入|in\b|Vin", part, re.I):
                add_probe("in")
                continue
            if re.search(r"地|gnd|公共端", part, re.I):
                add_probe("0")
                continue
            issues.append("看不懂探针位置「%s」。可用：输入节点 / 输出节点 / 地 / "
                          "<位号>两端" % part)

    if issues:
        raise NLParseError(issues, raw)

    # ---------- 7) 仿真默认值 ----------
    freq = source["freq"]
    if sim["stop"] is None:
        if period_m:
            sim["stop"] = int(period_m.group(1)) / freq
        else:
            sim["stop"] = 6.0 / freq          # 6 个周期
            notes.append("仿真时长：未指定 → 6 个周期 = %s s" % _fmt_value(sim["stop"]))
    if sim["sample_rate"] is None:
        sim["sample_rate"] = 200.0 * freq      # 每周期 200 点
        notes.append("采样率：未指定 → 200 × 频率 = %s Hz" % _fmt_value(sim["sample_rate"]))

    # ---------- 8) 装配 IR ----------
    comps_out = []
    src_pos = list(_LAYOUT_SRC)
    comps_out.append({
        "refdes": source["refdes"], "family": source["family"], "part": source["part"],
        "value": source["value"],
        "params": {str(k): v for k, v in source["params"].items()},
        "position": src_pos,
    })
    for i, comp in enumerate(passives):
        pos = list(_LAYOUT_PASSIVE[i] if i < len(_LAYOUT_PASSIVE)
                   else (500.0 + 200.0 * i, 400.0))
        comps_out.append({"refdes": comp["refdes"], "family": comp["family"],
                          "part": comp["part"], "value": comp["value"],
                          "params": {}, "position": pos})
    comps_out.append({"refdes": "GND1", "family": "POWER_SOURCES", "part": "GROUND",
                      "value": None, "params": {}, "position": list(_LAYOUT_GND)})

    d = {
        "version": IR_VERSION,
        # 名字里带位号和频率，两个不同频率的 RC 才不会互相覆盖产物
        "name": name or ("nl_%s_%gHz" % ("_".join([source["refdes"]] +
                                                  [p["refdes"] for p in passives]),
                                         source["freq"])),
        "components": comps_out,
        "nets": [{"name": n["name"], "pins": n["pins"]} for n in nets],
        "probes": probes,
        "simulation": {"analysis": sim["analysis"], "start": sim["start"],
                       "stop": sim["stop"], "step": sim["step"],
                       "sample_rate": sim["sample_rate"]},
    }
    ir = irmod.CircuitIR.from_dict(d)

    errs = ir.validate()
    if errs:
        if strict:
            raise NLParseError(["IR 校验失败（解析结果不合法）："] +
                               ["  - " + e for e in errs], raw)
        notes.append("IR 校验失败：%s" % errs)

    rep = {
        "text": raw,
        "normalized": t,
        "source": {"refdes": source["refdes"], "amp": source["value"],
                   "freq": source["freq"]},
        "chain": [p["refdes"] for p in passives],
        "nets": [{"name": n["name"], "pins": n["pins"]} for n in nets],
        "probes": [p["net"] for p in probes],
        "simulation": d["simulation"],
        "notes": notes,
        "warnings": ir.warnings(),
        "explain": explain(ir),
    }
    return ir, rep


def explain(ir):
    """把 IR 翻译成一句人话，用来确认"我理解的和你说的是不是同一件事"。"""
    src = next((c for c in ir.components if c.family == "SIGNAL_VOLTAGE_SOURCES"), None)
    chain = [c for c in ir.components
             if c.family in ("RESISTOR", "CAPACITOR")]
    parts = []
    if src:
        f = (src.params or {}).get(5)
        parts.append("%s 是 %s V / %s Hz 正弦源"
                     % (src.refdes, _fmt_value(src.value), _fmt_value(f)))
    for c in chain:
        unit = "Ω" if c.family == "RESISTOR" else "F"
        parts.append("%s 是 %s%s" % (c.refdes, _fmt_value(c.value), unit))
    if chain:
        path = " → ".join([src.refdes + ".+"] if src else [])
        for c in chain:
            path += " → %s" % c.refdes
        parts.append("串联顺序 %s → 地" % path)
    for n in ir.nets:
        parts.append("网络 %s = %s" % (n.name, " + ".join(n.pins)))
    if ir.probes:
        parts.append("探针 %s"
                     % "、".join("%s@%s" % (p.refdes, p.net) for p in ir.probes))
    s = ir.simulation
    parts.append("仿真 %s，0~%s s，采样率 %s Hz"
                 % (s.analysis, _fmt_value(s.stop), _fmt_value(s.sample_rate)))
    return "；".join(parts)


# ---------------------------------------------------------------- 命令行

def main(argv=None):
    ap = argparse.ArgumentParser(description="中文描述 -> Circuit IR")
    ap.add_argument("text", nargs="?", help="电路描述（一句话）")
    ap.add_argument("--file", help="从文本文件读取描述")
    ap.add_argument("-o", "--out", help="输出 IR JSON 路径")
    args = ap.parse_args(argv)

    text = args.text
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    if not text:
        ap.error("要么给一句话，要么用 --file")

    try:
        ir, rep = parse(text)
    except NLParseError as e:
        print("解析失败：")
        for it in e.issues:
            print("  - %s" % it)
        return 2

    print("=" * 70)
    print("我理解成：")
    print("  " + rep["explain"])
    for n in rep["notes"]:
        print("  · %s" % n)
    for w in rep["warnings"]:
        print("  ! %s" % w)
    print()
    print(ir.summary())
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        ir.save(args.out)
        print("\n写出 %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
