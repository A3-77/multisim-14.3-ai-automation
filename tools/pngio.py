# -*- coding: utf-8 -*-
"""纯标准库 PNG 读写 + 非背景像素包围盒。

为什么不用 PIL
--------------
`runtime/py32` 是 32 位 Python 3.11（Multisim COM 强制），里面只有 pywin32，
没有 Pillow，也没有 pip。截图链路要"抓窗口 -> 判断内容有没有出画"，
只需要"解码 + 统计包围盒 + 编码"，用 zlib 手写就够，也避免给运行时加依赖。
"""
import struct
import zlib


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(path):
    """读 PNG -> (w, h, channels, 像素字节串)。只支持 8 bit RGB/RGBA。"""
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG: %r" % path)
    pos, w, h, ct = 8, 0, 0, 0
    idat = bytearray()
    while pos < len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        tag = d[pos + 4:pos + 8]
        body = d[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", body[:10])
            if bd != 8 or ct not in (2, 6):
                raise ValueError("只支持 8bit RGB/RGBA，拿到 bd=%d ct=%d" % (bd, ct))
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    ch = 3 if ct == 2 else 4
    raw = zlib.decompress(bytes(idat))
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                left = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                left = line[i - ch] if i >= ch else 0
                ul = prev[i - ch] if i >= ch else 0
                line[i] = (line[i] + _paeth(left, prev[i], ul)) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, ch, out


def to_rgb(w, h, ch, data):
    if ch == 3:
        return data
    out = bytearray(w * h * 3)
    for i in range(w * h):
        out[i * 3:i * 3 + 3] = data[i * 4:i * 4 + 3]
    return out


def encode(path, w, h, rgb):
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return path


def light_bbox(path, region=None, thresh=245, step=2, min_run=20):
    """"白纸区域"包围盒：找图纸本身的位置。

    Multisim 画布上图纸是白的、图纸外是深灰，所以按"接近纯白"取包围盒
    就等于拿到图纸边界。用行/列计数而不是逐像素取极值，避免网格点或
    一根抗锯齿白线把范围撑大。
    """
    w, h, ch, data = decode(path)
    rgb = to_rgb(w, h, ch, data)
    x0, y0, x1, y1 = region or (0, 0, w, h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    cols = [0] * (x1 - x0)
    rows = [0] * (y1 - y0)
    for y in range(y0, y1, step):
        base = y * w * 3
        ry = (y - y0) // step
        for x in range(x0, x1, step):
            i = base + x * 3
            if rgb[i] >= thresh and rgb[i + 1] >= thresh and rgb[i + 2] >= thresh:
                cols[(x - x0) // step] += 1
                rows[ry] += 1
    ncol = len(cols)
    need_c = max(min_run // step, (y1 - y0) // step // 2)
    need_r = max(min_run // step, ncol // 2)
    xs = [x0 + i * step for i, v in enumerate(cols) if v >= need_c]
    ys = [y0 + i * step for i, v in enumerate(rows) if v >= need_r]
    if not xs or not ys:
        return None
    return (xs[0], ys[0], xs[-1], ys[-1])


def dark_bbox(path, region=None, thresh=150, step=2):
    """"深色像素"包围盒 —— 原理图画布上真正的内容（导线/元件/文字）是深色，
    网格点和图纸边框是浅灰，用亮度阈值就能把两者分开。"""
    w, h, ch, data = decode(path)
    rgb = to_rgb(w, h, ch, data)
    x0, y0, x1, y1 = region or (0, 0, w, h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    bx0, by0, bx1, by1 = x1, y1, -1, -1
    for y in range(y0, y1, step):
        base = y * w * 3
        for x in range(x0, x1, step):
            i = base + x * 3
            r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
            if (r * 299 + g * 587 + b * 114) // 1000 < thresh:
                if x < bx0:
                    bx0 = x
                if x > bx1:
                    bx1 = x
                if y < by0:
                    by0 = y
                if y > by1:
                    by1 = y
    if bx1 < 0:
        return None
    return (bx0, by0, bx1, by1)


def ink_bbox(path, region=None, bg_tol=10, step=2):
    """非背景像素的包围盒。region=(x0,y0,x1,y1) 限定统计范围。

    step 是采样步长（默认 2，1.3M 像素的窗口图也只要 0.4 s 左右）。
    背景色取 region 左上角像素 —— 原理图底色是纯白/纯灰，够用。
    """
    w, h, ch, data = decode(path)
    rgb = to_rgb(w, h, ch, data)
    x0, y0, x1, y1 = region or (0, 0, w, h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    i0 = (y0 * w + x0) * 3
    br, bg, bb = rgb[i0], rgb[i0 + 1], rgb[i0 + 2]
    bx0, by0, bx1, by1 = x1, y1, -1, -1
    for y in range(y0, y1, step):
        base = y * w * 3
        for x in range(x0, x1, step):
            i = base + x * 3
            if (abs(rgb[i] - br) > bg_tol or abs(rgb[i + 1] - bg) > bg_tol
                    or abs(rgb[i + 2] - bb) > bg_tol):
                if x < bx0:
                    bx0 = x
                if x > bx1:
                    bx1 = x
                if y < by0:
                    by0 = y
                if y > by1:
                    by1 = y
    if bx1 < 0:
        return None
    return (bx0, by0, bx1, by1)
