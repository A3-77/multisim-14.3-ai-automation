import re, sys, os, glob

PAT = re.compile(rb"[\x20-\x7e]{5,120}")
KEYS = [b"ewscr", b"ewlog", b"script", b"Script", b"angel", b"Angel", b"CommandLine", b"command line", b"/script", b"-script"]

def scan(path):
    try:
        d = open(path, "rb").read()
    except Exception:
        return
    found = []
    # ascii
    for m in PAT.finditer(d):
        s = m.group()
        if any(k in s for k in KEYS):
            found.append(("A", s.decode("latin-1")))
    # utf16
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){5,120}", d):
        s = m.group().decode("utf-16le", "ignore").encode("latin-1", "ignore")
        if any(k in s for k in KEYS):
            found.append(("W", s.decode("latin-1")))
    if found:
        print("=== %s (%d)" % (path, len(found)))
        seen = set()
        for enc, s in found:
            if s in seen: continue
            seen.add(s)
            print("   [%s] %s" % (enc, s[:140]))
        print()

root = r"C:/Program Files (x86)/National Instruments/Circuit Design Suite 14.3"
if not os.path.isdir(root):
    print("no root", root); sys.exit(1)
targets = []
for p in glob.glob(root + r"\**\*.exe", recursive=True) + glob.glob(root + r"\**\*.dll", recursive=True):
    targets.append(p)
print("scanning %d binaries" % len(targets))
for p in targets:
    base = os.path.basename(p).lower()
    if base in ("multisim.exe", "maininterface.dll", "scripting.dll", "schematiccapture.dll", "angelscript.dll", "msinterface.dll"):
        scan(p)
