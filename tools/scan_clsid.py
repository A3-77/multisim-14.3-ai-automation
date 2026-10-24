import winreg, os, sys

def scan(root, path, view=winreg.KEY_WOW64_32KEY):
    out = []
    try:
        k = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
    except OSError as e:
        print("open fail", path, e); return out
    i = 0
    while True:
        try:
            name = winreg.EnumKey(k, i); i += 1
        except OSError:
            break
        for sub in ("InprocServer32", "LocalServer32"):
            try:
                sk = winreg.OpenKey(k, name + "\\" + sub, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            try:
                val = winreg.QueryValueEx(sk, None)[0]
            except OSError:
                val = ""
            try:
                tid = winreg.QueryValueEx(sk, "ThreadingModel")[0]
            except OSError:
                tid = ""
            out.append((name, sub, val, tid))
    return out

entries = scan(winreg.HKEY_CLASSES_ROOT, "CLSID")
print("total CLSID w/ server:", len(entries))
hits = [e for e in entries if "multisim" in e[2].lower() or "electronics workbench" in e[2].lower()]
for h in hits:
    print("HIT", h)

# ProgID 名字里带 multisim / ewb 的
try:
    k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "", 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
    i = 0; progs = []
    while True:
        try:
            n = winreg.EnumKey(k, i); i += 1
        except OSError:
            break
        ln = n.lower()
        if "multisim" in ln or ln.startswith("ewb") or "electronicsworkbench" in ln:
            progs.append(n)
    print("\nProgID-like keys:", progs)
except OSError as e:
    print("progid scan fail", e)
