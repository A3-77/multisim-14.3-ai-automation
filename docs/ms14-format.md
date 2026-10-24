# `.ms14` 文件格式完整规范

> 本文所有结论都在本机 Multisim 14.3 上实测验证过，不是查资料猜的。
> 配套实现：`tools/dcl.py`（纯 Python，零依赖）、`vendor/blast.c`（C 版 ground truth）。

---

## 1. 总览

一个 `.ms14` 文件 = **36 字节 magic** + **16 字节首块头** + **若干 DCL 压缩块**。

```
偏移 0    36 字节  "MSMCompressedElectronicsWorkbenchXML"   (magic，含结尾 \0 则 36)
偏移 36   u32      明文总长度
偏移 40   u32      0（固定）
偏移 44   u32      第 1 块明文长度      (<= 900000)
偏移 48   u32      第 1 块压缩后长度
偏移 52   ...      第 1 块 DCL 压缩数据
          u32      第 N 块明文长度      ← 后续块只有 8 字节头，没有 magic/总长
          u32      第 N 块压缩后长度
          ...      第 N 块 DCL 压缩数据
```

- **小文件只有一块**，此时"明文总长度 == 第 1 块明文长度"。
- **超过 900000 字节分块**。实测 `PowerSupply.ms14` 首块 `unc=900000`，
  剩余 51053 字节是第二块（8 字节头 `114627 / 51045`）。
- 所有整数都是 **little-endian**。
- magic 有两种：`MSMCompressedElectronicsWorkbenchXML`（常见）和
  `CompressedElectronicsWorkbenchXML`。两种都要认。

### 解密出的是什么

明文是 **XML**，根元素路径（实测，`.ms14` 里没有外层 Project 包装，
解出来直接就是 Diagram 那一层）：

```
CIITDiagram
├── Elements                    ← 电气对象树
│   └── Item[Class=CiComponent|CiPort|CiNode|CiModel|CiProbeComp|CiCircuit]
└── Components
    └── CODComposite
        ├── Objects             ← 绘图对象树
        │   └── Item[ID=..., Class=CIITSymbolComp|CIITLinkComp|CIITProbeExtComponent|...]
        └── ReferencedComponents ← 引脚定义（CODPinComp，带 CenterX/CenterY 绝对坐标）
```

空白电路的明文是 **148367 字节**，`Elements` 里只有一个空的 `CiCircuit`，
`Objects` / `ReferencedComponents` 都是空的 —— 这是最干净的注入基底
（见 `out/ref/blank_circuit.xml`）。

---

## 2. 载荷算法 = PKWARE DCL (implode)

### 2.1 怎么定位到的

排查过程（按时间顺序，都是死路）：

1. 试过 zlib / lzma / lz4 / bzip2 —— 全部解不开。
2. 用 `strings` + 十六进制编辑器看文件头，只看到 magic 和一串长度字段。
3. **突破口**：下载 zlib 仓库的 `contrib/blast/blast.c`（Mark Adler 写的公版
   PKWARE DCL 解压器），读它的格式说明注释：

   > 第 0 字节 `lit`（0=字面量不编码 / 1=字面量用固定 Huffman 编码）
   > 第 1 字节 `dict` = log2(字典) − 6，合法值 4/5/6 → 1K/2K/4K 字典

4. 对照本机文件：头两个字节恒为 `01 06` = **字面量 Huffman 编码 + 4K 字典**。
5. 编译 `blast.c` → `vendor/dcltool.exe`，解 `blank.ms14` 得 **148367 字节**，
   与头部 `unc` 字段**分毫不差** → 算法确认。

> **经验**：遇到未知压缩格式，先去 zlib 的 `contrib/` 目录逛一圈。
> blast 就是为 PKWARE DCL 写的，而 DCL 是 90 年代 Windows 软件最爱用的格式之一。

### 2.2 位流细节

DCL 位流 **LSB first**（最低位先出）。

```
[8 bit] lit        0 或 1
[8 bit] dict       4 / 5 / 6
之后循环：
  [1 bit] 标志
    0 → 字面量：lit=0 时 [8 bit] 原始字节；lit=1 时查 litlen Huffman 表
    1 → 长度/距离对：
          [litlen Huffman] 长度符号
          [extra bits]     长度偏移
          [dist Huffman]   距离符号
          [extra bits]     距离低位
```

**长度符号表**（16 个符号）：

| 符号 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 2 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 12 | 16 | 24 | 40 | 72 | 136 | 264 |
| extra | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |

**结束码**：长度符号 **15**（base 264）+ 8 个额外位全 1 = **519**。
漏掉这个结束码是自研压缩器最常见的 bug（`blast` 会报"输入耗尽"）。

**距离编码**：
```python
shift = 2 if ln == 2 else dict_          # 长度为 2 时距离高位固定
dist  = (dist_symbol << shift) + extra_bits + 1
```

### 2.3 三个固定 Huffman 表

这三个表**写死在格式里**，所有 DCL 流都一样。紧凑编码规则：
**每个字节的高 4 位 = 重复次数−1，低 4 位 = 码长**。

```python
_LITLEN = bytes([
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
    9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
    7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
    8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
    44, 173])          # 98 字节
_LENLEN  = bytes([2, 35, 36, 53, 38, 23])        # 6 字节
_DISTLEN = bytes([2, 20, 53, 230, 247, 151, 248]) # 7 字节
```

展开函数：
```python
def _expand(rep):
    out = []
    for b in rep:
        out.extend([b & 15] * ((b >> 4) + 1))
    return out
```

### 2.4 解码算法（canonical Huffman）

与 `blast.c` 的 `decode()` 等价，逐位读、按码长分层比较：

```python
def _decode(b, table):
    count, symbol, _ = table
    code = first = index = 0
    ln = 1
    while True:
        code |= b.get(1) ^ 1        # 注意这个取反！
        c = count[ln]
        if code < first + c:
            return symbol[index + (code - first)]
        index += c
        first = (first + c) << 1
        code <<= 1
        ln += 1
```

> **坑**：`code |= b.get(1) ^ 1` 的取反很容易漏。漏了不会报错，会解出乱码。

### 2.5 压缩算法（我们自己的实现）

`implode()` 用 **LZ77 + 哈希链**，`lit=0`（字面量不编码，最省事且不会错）。

**两个关键坑**：

1. **哈希链必须"边扫描边插入"**。如果先把整条链建好再匹配，
   `head[key]` 会指向尚未处理的未来位置，算出负距离 → `KeyError: -1`。

   ```python
   head = {}; prev = [-1] * n
   def _insert(pos):
       if pos + 2 < n:
           key = data[pos:pos+3]
           prev[pos] = head.get(key, -1)
           head[key] = pos      # 必须在扫描到 pos 之后才插入
   ```

2. **编码表要从解码表反推，且必须按符号真实码长搜索**。
   用零填充暴力搜会让短码误判成别的符号（曾导致 `enc_len[15]` 得到 1 位码而非 7 位）。

   ```python
   def _build_encoder(table):
       _, _, length = table
       enc = {}
       for s, L in enumerate(length):
           if L == 0: continue
           for v in range(1 << L):              # 按真实码长 L 搜
               bits = [(v >> i) & 1 for i in range(L)]
               if _decode(_Bits(_pack(bits)), table) == s:
                   enc[s] = bits; break
       return enc
   ```

### 2.6 压缩率

| 文件 | 原始 | 我们压 | Multisim 压 |
| --- | --- | --- | --- |
| 空白电路 | 148367 B | 16272 B | 14481 B |
| 验收电路 | 209101 B | ~24 KB | — |

我们比 Multisim 大 12%，但**完全可用**（Multisim 能正常打开、正常渲染）。
要更逼近可以调 `min_match` / `chain` 上限 / 贪心策略，但没必要。

---

## 3. 容器读写实现

```python
def read_ms14(path):
    d = open(path, "rb").read()
    magic = MAGIC_MSM if d.startswith(MAGIC_MSM) else MAGIC_PLAIN
    base = len(magic)
    total, zero, c_unc, c_comp = struct.unpack_from("<IIII", d, base)
    pos = base + 16
    parts = []
    while True:
        x, used = explode(d[pos:pos + c_comp])
        assert used == c_comp, "压缩块长度不符"
        parts.append(x); pos += c_comp
        if pos >= len(d): break
        c_unc, c_comp = struct.unpack_from("<II", d, pos)   # 后续块 8 字节头
        pos += 8
    xml = b"".join(parts)
    assert len(xml) == total, "总长度不符"
    return xml, {...}


def write_ms14(path, xml, matches=True, chunk_limit=900000):
    chunks = [(len(p), implode(p, dict_=6, matches=matches))
              for p in (xml[i:i+chunk_limit] for i in range(0, len(xml), chunk_limit))]
    head = bytearray(MAGIC_MSM)
    head += struct.pack("<IIII", len(xml), 0, chunks[0][0], len(chunks[0][1]))
    ...  # 首块 16 字节头，后续块 8 字节头
```

---

## 4. 自检方法

```bash
# C 版（最快，用来交叉验证 Python 版）
gcc -O2 -o vendor/dcltool.exe vendor/dcltool.c vendor/blast.c
vendor/dcltool.exe d out/ref/acceptance.ms14 /tmp/acc.xml
wc -c /tmp/acc.xml        # 应该等于 XML 里 <总长> 字段

# Python 版
python tools/dcl.py out/ref/acceptance.ms14
```

**判断算法是否破解成功的黄金标准**：解出来的字节数必须和头部 `unc` 字段完全相等。
差一个字节都说明算法理解有误。

---

## 5. 已知未解之谜

- `&UNI<值>_uc<hash>` 里的单位哈希怎么算的。实测：电阻 `103a9`、电压 `100b5V`。
  目前用"从同类元件拷贝后缀"的方式绕过（`set_value()` 里保留原后缀）。
- magic 里那个变体（`CompressedElectronicsWorkbenchXML` 少 3 个字符）出现在什么场景，
  没见过实例，代码里做了兼容但没验证。
- `.ms14` 之外还有 `.ms12`（Multisim 12 格式）等，未研究。
