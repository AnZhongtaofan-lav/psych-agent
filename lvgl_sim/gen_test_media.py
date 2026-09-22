# -*- coding: utf-8 -*-
"""gen_test_media.py -- 生成测试用照片(p1~p3)和视频(v1), 直接产出可串口上传的 b64"""
import base64
import io
import os
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))


def save_b64(raw: bytes, name: str):
    txt = base64.b64encode(raw).decode("ascii")
    lines = [txt[i:i + 76] for i in range(0, len(txt), 76)]
    with open(os.path.join(OUT, name), "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("%s  raw=%d b64=%d" % (name, len(raw),
                                    os.path.getsize(os.path.join(OUT, name))))


def make_photo(idx):
    W, H = 480, 360
    im = Image.new("RGB", (W, H))
    dr = ImageDraw.Draw(im)
    palettes = [(30, 60, 120), (120, 40, 40), (30, 100, 70)]
    base = palettes[idx % 3]
    # 渐变背景
    for y in range(H):
        t = y / H
        dr.line([(0, y), (W, y)],
                fill=(int(base[0] + t * 60),
                      int(base[1] + t * 60),
                      int(base[2] + t * 60)))
    # 几个彩色圆
    for k in range(4):
        cx = 80 + k * 110
        cy = 120 + ((k * 53) % 80)
        r = 34 + (k * 7) % 22
        col = ((200 + k * 13) % 255, (90 + k * 60) % 255,
               (60 + k * 90) % 255)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    dr.rectangle([0, H - 56, W, H], fill=(10, 10, 24))
    dr.text((16, H - 42), "Photo %d - Psych AI Camera" % (idx + 1),
            fill=(0, 217, 255))
    dr.text((16, H - 22), "480x360 JPEG decoded by TJpgDec",
            fill=(200, 200, 200))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def make_video():
    W, H, FRAMES = 320, 240, 24
    out = io.BytesIO()
    for i in range(FRAMES):
        im = Image.new("RGB", (W, H), (12, 12, 28))
        dr = ImageDraw.Draw(im)
        # 移动的小球
        cx = 30 + i * ((W - 60) // FRAMES)
        cy = 80 + int(40 * (1 + (1 if (i // 6) % 2 == 0 else -1)))
        dr.ellipse([cx - 22, cy - 22, cx + 22, cy + 22],
                   fill=(0, 217, 255))
        # 底部色条
        dr.rectangle([0, H - 40, W, H], fill=(26, 26, 46))
        dr.text((8, H - 30), "MJPEG test  frame %02d/%d" % (i + 1, FRAMES),
                fill=(46, 213, 115))
        im.save(out, "JPEG", quality=70)
    return out.getvalue()


def main():
    for i in range(3):
        save_b64(make_photo(i), "p%d_b64.txt" % (i + 1))
    save_b64(make_video(), "v1_b64.txt")
    print("done")


if __name__ == "__main__":
    main()
