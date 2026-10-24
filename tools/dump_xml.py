# -*- coding: utf-8 -*-
"""把内存里所有 XML 文本段完整导出来，挑出电路文档本体。"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = wt.HANDLE
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "mem")
os.makedirs(OUT, exist_ok=True)


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def find_pid(exe="multisim.exe"):
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    pid = None
    while k32.Process32Next(snap, ctypes.byref(pe)):
        if pe.szExeFile.lower() == exe.encode():
            pid = pe.th32ProcessID
            break
    k32.CloseHandle(snap)
    return pid


def dump(pid):
    h = k32.OpenProcess(0x0410, False, pid)
    mbi = MBI()
    addr = 0
    blobs = []
    while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Protect in (0x02, 0x04, 0x20, 0x40, 0x80, 0x08):
            buf = ctypes.create_string_buffer(size)
            n = ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(n)):
                data = buf.raw[:n.value]
                i = 0
                while True:
                    i = data.find(b"<?xml", i)
                    if i < 0:
                        break
                    j = i
                    # 一段连续的可打印 XML 文本
                    while j < len(data) and (32 <= data[j] < 127 or data[j] in (9, 10, 13)) and j - i < 4_000_000:
                        j += 1
                    if j - i > 800:
                        blobs.append((base + i, data[i:j]))
                    i = j if j > i else i + 4
        addr = base + size
        if addr > 0x7FFFFFFF:
            break
    k32.CloseHandle(h)
    return blobs


with Multisim() as ms:
    c = ms.open(os.path.join(ROOT, "samples", "7812.ms12"))
    print("已打开:", c.name)
    time.sleep(2)
    pid = find_pid()
    blobs = dump(pid)
    print("找到 %d 段 XML" % len(blobs))
    blobs.sort(key=lambda b: -len(b[1]))
    for k, (addr, data) in enumerate(blobs[:8]):
        head = data[:160].decode("utf-8", "replace").replace("\n", " ")
        print("\n#%d 0x%08X %d bytes\n   %s" % (k, addr, len(data), head[:150]))
        with open(os.path.join(OUT, "blob%02d.xml" % k), "wb") as f:
            f.write(data)
