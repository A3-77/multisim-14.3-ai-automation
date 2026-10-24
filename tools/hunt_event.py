import re, os, glob

root = r"C:/Program Files (x86)/National Instruments/Circuit Design Suite 14.3"
KEYS = ["Regrassion", "RegressionTest", "AppCommandFrom", "ExternalCommandLine",
        "ReceiveCPFromMSM", "Internal mode", "commandlog", "CEventHandler",
        "MSMCommand", "AppCommand", "EventHandler"]

def strings(d):
    out = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){3,200}", d):
        out.append((m.start(), m.group().decode("utf-16le", "ignore")))
    for m in re.finditer(rb"[\x20-\x7e]{4,200}", d):
        out.append((m.start(), m.group().decode("latin-1")))
    out.sort()
    return out

files = glob.glob(root + r"\**\*.dll", recursive=True) + glob.glob(root + r"\**\*.exe", recursive=True)
for f in files:
    try:
        d = open(f, "rb").read()
    except Exception:
        continue
    if not any(k.encode("latin-1") in d or k.encode("utf-16le") in d for k in ["Regrassion", "AppCommandFrom", "ExternalCommandLine"]):
        continue
    ss = strings(d)
    print("=" * 70)
    print(os.path.relpath(f, root), len(d))
    for i, (off, s) in enumerate(ss):
        if any(k in s for k in KEYS):
            print("  @0x%06x %s" % (off, s[:160]))
