# -*- coding: utf-8 -*-
"""直接调用 NI 自己的压缩函数 CCompressUtil::compress（在 Database.dll 里）。

为什么这么干：Multisim 的 .ms14 用的是 PKWARE DCL（ZIP method 6 / implode），
Python 没有现成实现。与其重写一个可能对不上的压缩器，不如直接借它的。

C++ 签名（mangled）：
    ?compress@CCompressUtil@@QAE_NPBDKPAPADPAK@Z
    bool CCompressUtil::compress(const char* in, unsigned long inLen,
                                 char** out, unsigned long* outLen)
QAE = public __thiscall。__thiscall 把 this 放 ECX，ctypes 只会按 cdecl 压栈，
所以需要一小段机器码把栈上的第一个参数搬到 ECX：

    58        pop  eax      ; 取回返回地址
    59        pop  ecx      ; this -> ECX
    50        push eax      ; 返回地址压回去
    E9 rel32  jmp  target   ; 跳到真正的函数

这样栈布局就从 [ret][this][in][len][out][outLen] 变成 [ret][in][len][out][outLen]。
"""
import ctypes
import ctypes.wintypes as w
import os
import sys

INST = r"C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.3"
k32 = ctypes.windll.kernel32

SYM_COMPRESS = b"?compress@CCompressUtil@@QAE_NPBDKPAPADPAK@Z"
SYM_INITIAL = b"?initial@CCompressUtil@@AAEXXZ"


def make_thunk(target, this_val):
    """生成 pop/pop/push/jmp 这段跳板，返回可调用地址。"""
    code = bytearray(b"\x58\x59\x50\xe9")
    k32.VirtualAlloc.restype = ctypes.c_void_p
    mem = k32.VirtualAlloc(None, 64, 0x3000, 0x40)  # MEM_COMMIT|RESERVE, PAGE_EXECUTE_READWRITE
    if not mem:
        raise OSError("VirtualAlloc 失败")
    rel = target - (mem + 8)
    code += (rel & 0xFFFFFFFF).to_bytes(4, "little", signed=False)
    ctypes.memmove(mem, bytes(code), len(code))
    return mem


def load_dll():
    os.add_dll_directory(INST)
    os.environ["PATH"] = INST + ";" + os.environ.get("PATH", "")
    return ctypes.WinDLL(os.path.join(INST, "Database.dll"))


def get_proc(dll, sym):
    k32.GetProcAddress.restype = ctypes.c_void_p
    k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    addr = k32.GetProcAddress(ctypes.c_void_p(dll._handle), sym)
    if not addr:
        raise RuntimeError("找不到符号 %r" % sym)
    return addr


def main():
    data = sys.argv[1].encode() if len(sys.argv) > 1 else b"hello world " * 40
    if os.path.exists(sys.argv[1] if len(sys.argv) > 1 else ""):
        data = open(sys.argv[1], "rb").read()
    print("输入 %d 字节" % len(data))

    dll = load_dll()
    print("Database.dll 加载 OK")
    addr = get_proc(dll, SYM_COMPRESS)
    print("compress @ 0x%x" % addr)

    # 造一个假对象：CCompressUtil 大概只有一个 vtable 指针 + 少量成员
    this_buf = ctypes.create_string_buffer(512)
    this_ptr = ctypes.addressof(this_buf)

    try:
        init_addr = get_proc(dll, SYM_INITIAL)
        thunk_init = make_thunk(init_addr, this_ptr)
        fn_init = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)(thunk_init)
        fn_init(this_ptr)
        print("initial() 调用 OK")
    except Exception as e:
        print("initial() 跳过:", repr(e))

    thunk = make_thunk(addr, this_ptr)
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_char_p,
                               ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                               ctypes.POINTER(ctypes.c_ulong))
    fn = proto(thunk)

    out_ptr = ctypes.c_void_p(0)
    out_len = ctypes.c_ulong(0)
    ok = fn(this_ptr, data, len(data), ctypes.byref(out_ptr), ctypes.byref(out_len))
    print("compress 返回:", ok, "out_len:", out_len.value, "out_ptr:", out_ptr.value)
    if ok and out_ptr.value and out_len.value:
        blob = ctypes.string_at(out_ptr.value, out_len.value)
        print("压缩后 %d 字节，头部: %s" % (len(blob), blob[:48].hex(" ")))
        outpath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "out", "dcl_test.bin")
        with open(outpath, "wb") as f:
            f.write(blob)
        print("已写入", outpath)


if __name__ == "__main__":
    main()
