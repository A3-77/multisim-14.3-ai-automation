# -*- coding: utf-8 -*-
"""暴力试 LZSS / LZW 家族，看能不能解出 XML。"""
import os, sys

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
raw = open(os.path.join(OUT, "blank.xml"), "rb").read()
PAY = raw[56:]
print("payload:", len(PAY), "bytes")


def score(data):
    if not data:
        return 0
    printable = sum(1 for c in data[:4000] if 9 <= c <= 13 or 32 <= c < 127)
    return printable / min(len(data), 4000)


def ok(data):
    if len(data) < 200:
        return False
    head = data[:400]
    return (head.lstrip()[:1] == b"<") or (b"<?xml" in head) or (b"<MSM" in head)


def lzss(data, off_bits, len_bits, min_len, lsb_first, off_bias, len_bias, pack="split"):
    """经典 LZSS：标志位每 8 个一组，1=字面量，0=回溯引用。"""
    out = bytearray()
    pos = 0
    n = len(data)
    win = 1 << off_bits
    mask_off = win - 1
    mask_len = (1 << len_bits) - 1
    while pos < n:
        flags = data[pos]
        pos += 1
        for i in range(8):
            if pos >= n:
                break
            bit = (flags >> i) & 1 if lsb_first else (flags >> (7 - i)) & 1
            if bit:
                out.append(data[pos])
                pos += 1
            else:
                if pos + 1 >= n:
                    return bytes(out)
                b0, b1 = data[pos], data[pos + 1]
                pos += 2
                if pack == "split":
                    # 低 off_bits 放偏移，其余放长度
                    val = b0 | (b1 << 8)
                    off = val & mask_off
                    ln = (val >> off_bits) & mask_len
                else:
                    off = ((b1 & 0xF0) << 4) | b0
                    ln = b1 & 0x0F
                ln += len_bias
                off += off_bias
                if ln <= 0 or off <= 0 or off > len(out):
                    return bytes(out)
                start = len(out) - off
                for k in range(ln):
                    out.append(out[start + k])
            if len(out) > 400000:
                return bytes(out)
    return bytes(out)


def lzw(data, init_bits, lsb=True, clear=256, max_bits=12):
    out = bytearray()
    dic = {i: bytes([i]) for i in range(256)}
    nxt = clear + 1 if clear else 256
    bits = init_bits
    buf = 0
    nbits = 0
    prev = None
    for byte in data:
        buf |= (byte << nbits) if lsb else (byte << (24 - nbits))
        nbits += 8
        while nbits >= bits:
            code = (buf & ((1 << bits) - 1)) if lsb else ((buf >> (32 - bits)) & ((1 << bits) - 1))
            buf = (buf >> bits) if lsb else (buf & ((1 << (32 - bits)) - 1))
            nbits -= bits
            if clear is not None and code == clear:
                dic = {i: bytes([i]) for i in range(256)}
                nxt = clear + 1
                bits = init_bits
                prev = None
                continue
            if code in dic:
                entry = dic[code]
            elif prev is not None:
                entry = prev + prev[:1]
            else:
                return bytes(out)
            out.append(0)  # placeholder
            out = out[:-1] + entry if False else out
            out = bytearray(out) + entry
            if prev is not None and nxt < 4096:
                dic[nxt] = prev + entry[:1]
                nxt += 1
                if nxt >= (1 << bits) and bits < max_bits:
                    bits += 1
            prev = entry
            if len(out) > 400000:
                return bytes(out)
    return bytes(out)


best = []
print("\n--- LZSS 变体 ---")
for off_bits in (11, 12, 13, 16):
    for len_bits in (4, 5, 8):
        for min_len in (1, 2, 3):
            for lsb in (True, False):
                for ob in (0, -1):
                    for pack in ("split", "nibble"):
                        if pack == "nibble" and (off_bits != 12 or len_bits != 4):
                            continue
                        try:
                            d = lzss(PAY, off_bits, len_bits, min_len, lsb, ob, min_len, pack)
                        except Exception:
                            continue
                        s = score(d)
                        best.append((s, len(d), ("lzss", off_bits, len_bits, min_len, lsb, ob, pack)))
                        if ok(d):
                            print("!!! HIT", best[-1][2], "len", len(d))
                            print(d[:400])
                            sys.exit(0)

print("\n--- LZW 变体 ---")
for init_bits in (9, 10, 11):
    for lsb in (True, False):
        for clear in (256, None):
            try:
                d = lzw(PAY, init_bits, lsb, clear)
            except Exception:
                continue
            s = score(d)
            best.append((s, len(d), ("lzw", init_bits, lsb, clear)))
            if ok(d):
                print("!!! HIT", best[-1][2], "len", len(d))
                print(d[:400])
                sys.exit(0)

best.sort(reverse=True)
print("\n最佳猜测：")
for b in best[:8]:
    print("  score=%.2f len=%d %s" % b)
