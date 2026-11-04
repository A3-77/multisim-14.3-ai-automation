# -*- coding: utf-8 -*-
"""把 Multisim 截图的浅灰网格点/图纸灰底刷成纯白（导线文字是 0~20，不受影响）。

用法：python hw_clean_schematic.py <png> [阈值]
"""
import sys
from PIL import Image


def clean(path, thr=118, pad=6):
    im = Image.open(path).convert("RGB")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y]
            if r >= thr and g >= thr and b >= thr:
                px[x, y] = (255, 255, 255)

    # 四周若有残留的图纸边框线，再收一圈：非纯白像素的包围盒
    W, H = im.size
    g = im.convert("L")
    mask = g.point(lambda v: 255 if v < 245 else 0)
    bbox = mask.getbbox()
    if bbox:
        l, t, r, b = bbox
        im = im.crop((max(0, l - pad), max(0, t - pad),
                      min(W, r + pad), min(H, b + pad)))
    im.save(path)
    print("->", path, im.size)


if __name__ == "__main__":
    p = sys.argv[1]
    thr = int(sys.argv[2]) if len(sys.argv) > 2 else 118
    clean(p, thr)
