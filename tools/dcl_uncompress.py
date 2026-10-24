# -*- coding: utf-8 -*-
"""调用 CCompressUtil::uncompress(CByteArray&) 解压 .ms14 里的数据。

MFC CByteArray 的内存布局（x86）：
    +0  vptr
    +4  BYTE*  m_pData
    +8  INT_PTR m_nSize
    +12 INT_PTR m_nMaxSize
    +16 INT_PTR m_nGrowBy

我们手工拼一个，让 MFC 自己去 realloc（所以缓冲区必须用 malloc 分配）。
"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl_compress as D

SYM_UNCOMPRESS = b"?uncompress@CCompressUtil@@QAE_NAAVCByteArray@@@Z"

libc = ctypes.CDLL("msvcrt.dll")
libc.malloc.restype = ctypes.c_void_p
libc.malloc.argtypes = [ctypes.c_size_t]
libc.realloc.restype = ctypes.c_void_p
libc.realloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t]


class CByteArray(ctypes.Structure):
    _fields_ = [("vptr", ctypes.c_void_p),
                ("m_pData", ctypes.c_void_p),
                ("m_nSize", ctypes.c_ssize_t),
                ("m_nMaxSize", ctypes.c_ssize_t),
                ("m_nGrowBy", ctypes.c_ssize_t)]


class Codec:
    def __init__(self):
        self.dll = D.load_dll()
        self.this = ctypes.create_string_buffer(512)
        self.this_ptr = ctypes.addressof(self.this)
        try:
            ia = D.get_proc(self.dll, D.SYM_INITIAL)
            ctypes.WINFUNCTYPE(None, ctypes.c_void_p)(D.make_thunk(ia, self.this_ptr))(self.this_ptr)
        except Exception:
            pass
        ca = D.get_proc(self.dll, D.SYM_COMPRESS)
        self._c = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_char_p,
                                     ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.POINTER(ctypes.c_ulong))(D.make_thunk(ca, self.this_ptr))
        ua = D.get_proc(self.dll, SYM_UNCOMPRESS)
        self._u = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.POINTER(CByteArray))(D.make_thunk(ua, self.this_ptr))

    def compress(self, data):
        o = ctypes.c_void_p(0)
        n = ctypes.c_ulong(0)
        ok = self._c(self.this_ptr, data, len(data), ctypes.byref(o), ctypes.byref(n))
        if not ok:
            raise RuntimeError("compress 失败")
        return ctypes.string_at(o.value, n.value) if n.value else b""

    def uncompress(self, blob):
        buf = libc.malloc(len(blob) + 1)
        ctypes.memmove(buf, blob, len(blob))
        arr = CByteArray(0, buf, len(blob), len(blob), 0)
        ok = self._u(self.this_ptr, ctypes.byref(arr))
        if not ok:
            raise RuntimeError("uncompress 失败")
        return ctypes.string_at(arr.m_pData, arr.m_nSize), arr.m_nSize


def payload_of_ms14(path):
    """.ms14 -> (头部字段, 压缩数据)"""
    d = open(path, "rb").read()
    if d.startswith(b"MSM"):
        magic = b"MSMCompressedElectronicsWorkbenchXML"
    else:
        magic = b"CompressedElectronicsWorkbenchXML"
    assert d.startswith(magic), "magic 不匹配: %r" % d[:40]
    unc, z, unc2, comp = __import__("struct").unpack_from("<IIII", d, len(magic))
    return {"magic": magic.decode(), "unc": unc, "zero": z, "unc2": unc2, "comp": comp,
            "rest": len(d) - len(magic) - 16}, d[len(magic) + 16:]


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "blob00.dcl")
    blob = open(path, "rb").read()
    print("读入 %s (%d 字节)" % (os.path.basename(path), len(blob)))
    c = Codec()
    print("编解码器就绪")
    out, n = c.uncompress(blob)
    print("解压 -> %d 字节" % n)
    print("开头:", repr(out[:120]))
    outpath = os.path.join(ROOT, "out", "uncompressed.bin")
    open(outpath, "wb").write(out)
    print("已写入", outpath)
