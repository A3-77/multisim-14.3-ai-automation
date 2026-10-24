# -*- coding: utf-8 -*-
"""
setup_env.py —— 重建 runtime\\py32（32 位 Python + pywin32）

正常情况下不需要跑：仓库里已经带好了 runtime\\py32，直接 run.bat 就能用。
只有在 runtime 被删掉、或者想换机器复制时，才用任意 Python（64 位也行）执行：

    python setup_env.py

它做三件事：
  1. 下载 python-3.11.9-embed-win32.zip 并解压到 runtime\\py32
  2. 下载 pywin32 的 32 位 wheel 并解包进 site-packages
  3. 写 python311._pth，让解释器能找到 site-packages
"""

import io
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RT = os.path.join(HERE, "runtime", "py32")

PY_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-win32.zip"


def download(url, label):
    print("  下载 %s ..." % label)
    req = urllib.request.Request(url, headers={"User-Agent": "msc-setup"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    if os.path.exists(os.path.join(RT, "python.exe")):
        print("runtime 已存在：%s" % RT)
        print("要重建就先把 runtime 目录删掉再跑。")
        return 0

    os.makedirs(RT, exist_ok=True)

    print("[1/3] 32 位 Python 3.11.9")
    data = download(PY_URL, "python-3.11.9-embed-win32.zip")
    zipfile.ZipFile(io.BytesIO(data)).extractall(RT)

    print("[2/3] pywin32 (win32 wheel)")
    import json
    meta = json.load(urllib.request.urlopen("https://pypi.org/pypi/pywin32/json"))
    cand = [f for f in meta["urls"]
            if "cp311" in f["filename"] and "win32" in f["filename"] and f["filename"].endswith(".whl")]
    if not cand:
        raise RuntimeError("PyPI 上找不到 cp311-win32 的 pywin32 wheel")
    data = download(cand[0]["url"], cand[0]["filename"])
    zipfile.ZipFile(io.BytesIO(data)).extractall(os.path.join(RT, "Lib", "site-packages"))

    print("[3/3] 配置 _pth")
    with open(os.path.join(RT, "python311._pth"), "w") as f:
        f.write("python311.zip\n.\nLib/site-packages\nimport site\n")

    print("\n完成。验证：")
    os.system('"%s" -c "import pythoncom, win32com.client; print(\'pywin32 OK\')"' %
              os.path.join(RT, "python.exe"))
    print("\n接着跑:  run.bat selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
