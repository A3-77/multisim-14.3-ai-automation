# -*- coding: utf-8 -*-
"""裁剪 + 放大截图，用于检查电路画得对不对。"""
import sys
from PIL import Image

src = sys.argv[1]
dst = sys.argv[2]
box = tuple(int(x) for x in sys.argv[3].split(","))   # l,t,r,b
scale = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0

im = Image.open(src)
print("原图", im.size)
c = im.crop(box)
c = c.resize((int(c.width * scale), int(c.height * scale)), Image.LANCZOS)
c.save(dst)
print("->", dst, c.size)
