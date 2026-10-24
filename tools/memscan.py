# -*- coding: utf-8 -*-
"""从运行中的 Multisim 进程里捞明文 XML。

.ms14 在内存里会先被解压成一整块明文 XML 放在某个缓冲区，
这里按区域扫可读内存，找 <?xml ... ?> 开头、</ElectronicsWorkbench> 结尾的整块。
"""
import ctypes
import ctypes.wintypes as w

k32 = ctypes.windll.kernel32

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_READABLE = (0x02, 0x04, 0x20, 0x40, 0x80, 0x08)  # RO/RW/WC/DC/EX/RWX


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", w.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", w.DWORD), ("Protect", w.DWORD), ("Type", w.DWORD)]


def read_regions(pid, max_region=64 * 1024 * 1024):
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        raise OSError("OpenProcess 失败: %d" % ctypes.GetLastError())
    out = []
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()
    n = 0
    while addr < 0x7FFFFFFF:
        got = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not got:
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize or 0
        if size == 0:
            break
        if mbi.State == MEM_COMMIT and mbi.Protect in PAGE_READABLE and 0 < size <= max_region:
            buf = ctypes.create_string_buffer(size)
            read = ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(read)):
                out.append((base, buf.raw[:read.value]))
                n += 1
        addr = base + size
    k32.CloseHandle(h)
    return out, n


def find_xml(pid, end_tag=b"</ElectronicsWorkbench>", start_tag=b"<?xml", min_len=1000):
    regions, nreg = read_regions(pid)
    hits = []
    for base, data in regions:
        pos = 0
        while True:
            i = data.find(start_tag, pos)
            if i < 0:
                break
            j = data.find(end_tag, i)
            if j < 0:
                break
            j += len(end_tag)
            blob = data[i:j]
            if len(blob) >= min_len:
                hits.append((base + i, blob))
            pos = j
    # 去重（同一份文档可能在多处出现）
    seen = {}
    for addr, blob in hits:
        seen.setdefault(len(blob), []).append((addr, blob))
    return seen, len(regions), nreg


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1])
    seen, nreg, nread = find_xml(pid)
    print("扫了 %d 个可读区域（读到 %d 块）" % (nreg, nread))
    for ln in sorted(seen, reverse=True):
        print("  %8d 字节 x%d  @0x%x" % (ln, len(seen[ln]), seen[ln][0][0]))
