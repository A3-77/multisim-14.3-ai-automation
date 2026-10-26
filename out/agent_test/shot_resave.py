# -*- coding: utf-8 -*-
"""让 Multisim 自己另存一次再截图 —— 看保存时会不会重建绘图对象。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import msc   # noqa: E402

SRC = os.path.join(ROOT, "out", "mcp", "sessions", "c-eccf480d70",
                   "agent_rc_500hz.ms14")
DIR = os.path.join(ROOT, "out", "agent_test")


def main():
    ms = msc.Multisim()
    circ = ms.open(SRC)
    print("opened comps=%s" % (circ.components(),))

    saved = os.path.join(DIR, "resaved_by_multisim.ms14")
    try:
        circ.save_as(saved)
        print("save_as -> %s (%d 字节)"
              % (saved, os.path.getsize(saved) if os.path.exists(saved) else -1))
    except Exception as e:
        print("save_as 失败: %s" % e)
        return
    try:
        circ.stop()
    except Exception:
        pass
    time.sleep(1.0)

    # 重新打开另存后的文件再截图
    ms2 = msc.Multisim()
    c2 = ms2.open(saved)
    print("reopened comps=%s" % (c2.components(),))
    out = os.path.join(DIR, "shot_resaved.png")
    c2.snapshot(out)
    print("shot -> %d 字节" % os.path.getsize(out))
    try:
        c2.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
