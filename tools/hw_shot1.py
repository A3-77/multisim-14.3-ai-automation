# -*- coding: utf-8 -*-
"""生成"展示用"电路图（不带探针）并截图。

裁剪策略：自己做墨迹包围盒，并剔除贯穿画面的长直线（图纸边框/刻度带）。
screenshot.circuit_bbox 依赖 sheet_rect 屏蔽边框，图纸一旦放大出界就失效。

缩放：Ctrl+滚轮的方向在不同机器上实测不一致，所以先探一次方向再闭环；
每一轮都先把内容拖到画布正中，避免放大时被边沿裁掉。
"""
import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ir_compile        # noqa: E402
import hw_lab1           # noqa: E402
import screenshot as SS  # noqa: E402
from PIL import Image    # noqa: E402

OUT = os.path.join(ROOT, "out", "hw1")
IMG = os.path.join(OUT, "img")
u = ctypes.windll.user32
LUM = 110


def ink_bbox(png, hwnd):
    """画布内电路笔画的包围盒。

    不做"剔除长直线"——电源轨和地母线本身就是贯穿画面的长线，
    剔掉会把电路的上下边界一起切掉。图纸边框如果可见，交给
    trim_border_lines() 在裁剪之后处理。
    """
    im = Image.open(png).convert("L")
    W, H = im.size
    reg = SS.canvas_region(hwnd)
    l, t, _r, _b = SS.rect(hwnd)
    x0 = max(0, reg[0] - l) + 4
    y0 = max(0, reg[1] - t) + 4
    x1 = min(W, reg[2] - l) - 4
    y1 = min(H, reg[3] - t) - 4
    px = im.load()

    bx0, by0, bx1, by1 = x1, y1, -1, -1
    for y in range(y0, y1):
        row = [x for x in range(x0, x1) if px[x, y] < LUM]
        if not row:
            continue
        by0 = min(by0, y)
        by1 = max(by1, y)
        bx0 = min(bx0, row[0])
        bx1 = max(bx1, row[-1])
    if bx1 < 0:
        return None, (x0, y0, x1, y1)
    return (bx0, by0, bx1, by1), (x0, y0, x1, y1)


def trim_border_lines(im, thr=245, ratio=0.80, band=60):
    """裁掉紧贴图片边缘的图纸框线（整列/整行几乎全是深色）。"""
    g = im.convert("L")
    W, H = g.size
    px = g.load()

    def col_dark(x):
        n = sum(1 for y in range(H) if px[x, y] < thr)
        return n > ratio * H

    def row_dark(y):
        n = sum(1 for x in range(W) if px[x, y] < thr)
        return n > ratio * W

    left = 0
    for x in range(min(band, W)):
        if col_dark(x):
            left = x + 1
    right = W
    for x in range(W - 1, max(W - band, -1), -1):
        if col_dark(x):
            right = x
    top = 0
    for y in range(min(band, H)):
        if row_dark(y):
            top = y + 1
    bottom = H
    for y in range(H - 1, max(H - band, -1), -1):
        if row_dark(y):
            bottom = y
    if (left, top, right, bottom) != (0, 0, W, H):
        im = im.crop((left, top, right, bottom))
    return im


def measure(h, tmp):
    SS.capture_window(h, tmp)
    bb, reg = ink_bbox(tmp, h)
    if not bb:
        return None
    m = (bb[0] - reg[0], bb[1] - reg[1], reg[2] - bb[2], reg[3] - bb[3])
    fill = ((bb[2] - bb[0]) * (bb[3] - bb[1])) / float(
        (reg[2] - reg[0]) * (reg[3] - reg[1]))
    return {"bb": bb, "reg": reg, "m": m, "fill": fill}


def pan_center(h, tmp, rounds=4):
    for _ in range(rounds):
        r = measure(h, tmp)
        if not r:
            return
        bb, reg = r["bb"], r["reg"]
        dx = (reg[0] + reg[2]) // 2 - (bb[0] + bb[2]) // 2
        dy = (reg[1] + reg[3]) // 2 - (bb[1] + bb[3]) // 2
        if abs(dx) <= 8 and abs(dy) <= 8:
            return
        l, t, rr, bb2 = SS.rect(h)
        cx, cy = (l + rr) // 2, (t + bb2) // 2
        SS._drag_middle(cx, cy, cx + dx / 1.25, cy + dy / 1.25)


def detect_sign(h, tmp):
    a = measure(h, tmp)
    SS._zoom(h, +2)
    b = measure(h, tmp)
    if not a or not b:
        return +1
    return +1 if b["fill"] > a["fill"] else -1


def fit_and_crop(ms14, out_png):
    h = SS.open_in_gui(ms14)
    print("  hwnd=%d rect=%s" % (h, SS.rect(h)))
    SS.foreground(h)
    time.sleep(0.9)

    tmp = os.path.join(IMG, "_fit_probe.png")
    # 打开时的默认缩放本来就够大（实测内容占画布 ~89%），只是偏在一角。
    # 不再闭环缩放：Multisim 会丢 Ctrl+滚轮消息，方向探测也不稳定，
    # 越调越糟。这里只做居中平移，然后按墨迹包围盒裁。
    for i in range(5):
        r = measure(h, tmp)
        if not r:
            print("  第 %d 轮：无墨迹" % i)
            break
        print("  第 %d 轮 fill=%.3f margins=%s" % (i, r["fill"], r["m"]))
        if min(r["m"]) >= 10:
            break
        pan_center(h, tmp)
    pan_center(h, tmp)
    SS.capture_window(h, out_png)
    bb, reg = ink_bbox(out_png, h)
    im = Image.open(out_png)
    pad = 20
    box = (max(0, bb[0] - pad), max(0, bb[1] - pad),
           min(im.width, bb[2] + pad), min(im.height, bb[3] + pad))
    im = im.crop(box)
    im = trim_border_lines(im)

    # 图纸的浅灰网格点（亮度正好 150）在文档里显得脏，统一刷成纯白；
    # 导线/文字/符号是 0~20，不受影响。阈值必须 <=150，用 >150 会漏掉。
    im = im.convert("RGB")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y]
            if r >= 118 and g >= 118 and b >= 118:
                px[x, y] = (255, 255, 255)

    # 刷白之后按非纯白像素再收紧一次，去掉底部残留的空白带
    g2 = im.convert("L").point(lambda v: 255 if v < 245 else 0)
    bb2 = g2.getbbox()
    if bb2:
        l, t, r2, b2 = bb2
        pad2 = 10
        im = im.crop((max(0, l - pad2), max(0, t - pad2),
                      min(im.width, r2 + pad2), min(im.height, b2 + pad2)))
    im.save(out_png)
    print("  裁到 %s -> %s" % (box, im.size))
    if os.path.isfile(tmp):
        os.remove(tmp)
    return out_png


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "t1"
    if which == "t2":
        import hw_sch2
        ms14, rep, n = hw_sch2.compile_display()
        print("编译 %d 字节 -> %s（隐藏引脚小字 %d 处）" % (rep["bytes"], ms14, n))
        p = fit_and_crop(ms14, os.path.join(IMG, "task2_schematic.png"))
        print("OK ->", p)
        return
    import hw_sch1
    ms14 = os.path.join(OUT, "sch1_p20.ms14")
    rep = ir_compile.compile_ir(hw_sch1.build(), ms14, verbose=False)
    print("编译 %d 字节 -> %s" % (rep["bytes"], ms14))
    p = fit_and_crop(ms14, os.path.join(IMG, "task1_schematic.png"))
    print("OK ->", p)


if __name__ == "__main__":
    main()
