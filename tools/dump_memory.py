# -*- coding: utf-8 -*-
"""
从运行中的 Multisim 进程内存里找解压后的电路 XML。
思路：Multisim 打开电路时，XML 一定以明文存在于堆里。
找到后就能拿到文件结构（甚至可能发现它支持不压缩的写法）。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msc import Multisim

k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = wt.HANDLE


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
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


def scan(pid, needles, max_region=64 * 1024 * 1024):
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        raise RuntimeError("OpenProcess 失败: %d" % ctypes.get_last_error())
    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    hits = []
    total = 0
    while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        # 只读可读的已提交页
        if mbi.State == 0x1000 and mbi.Protect in (0x02, 0x04, 0x20, 0x40, 0x80, 0x08):
            buf = ctypes.create_string_buffer(size)
            read = ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(read)):
                data = buf.raw[:read.value]
                total += len(data)
                for n in needles:
                    idx = 0
                    while True:
                        i = data.find(n, idx)
                        if i < 0:
                            break
                        hits.append((base + i, n, data[i:i + 400]))
                        idx = i + 1
                        if len(hits) > 200:
                            break
        addr = base + size
        if addr > 0x7FFFFFFF:
            break
    k32.CloseHandle(h)
    print("扫描了 %.1f MB 内存" % (total / 1048576.0))
    return hits


with Multisim() as ms:
    c = ms.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "7812.ms12"))
    print("电路已打开:", c.name)
    time.sleep(2)
    pid = find_pid()
    print("pid:", pid)
    hits = scan(pid, [b"<?xml", b"<MSM", b"<Circuit", b"ElectronicsWorkbench"])
    print("命中:", len(hits))
    seen = set()
    for addr, needle, ctx in hits[:12]:
        key = ctx[:60]
        if key in seen:
            continue
        seen.add(key)
        print("\n--- 0x%08X [%s] ---" % (addr, needle.decode("latin-1")))
        print(ctx[:300].decode("utf-8", "replace"))
