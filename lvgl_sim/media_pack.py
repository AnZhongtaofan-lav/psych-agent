# -*- coding: utf-8 -*-
"""
media_pack.py -- 把电脑上的照片/视频打包成可串口上传的 base64 文件
==================================================================
板子程序只认 /tmp/media/ 下的固定文件名:
  照片: p1.jpg p2.jpg ... p8.jpg   (JPEG, 建议 <=480x360)
  视频: v1.mjpeg v2.mjpeg          (MJPEG 帧序列, 320x240@10fps)

准备依赖(可选, 但强烈建议装):
  pip install pillow imageio-ffmpeg

用法:
  python media_pack.py photo 照片1.jpg 照片2.png ...
      -> 生成 p1_b64.txt p2_b64.txt ...
  python media_pack.py video 手机录像.mp4
      -> 生成 v1_b64.txt ...

上传到板子 (每个文件重复一次):
  1. 板子串口执行:  busybox cat > /tmp/media/p1.b64
  2. SecureCRT: 传输 -> 发送ASCII -> 选 p1_b64.txt, 完成后 Ctrl+C
  3. 板子执行:     busybox base64 -d /tmp/media/p1.b64 > /tmp/media/p1.jpg
  4. 在板子程序里切到 PHOTOS/VIDEO 页 (程序启动时扫描一次;
     传完重启 /tmp/gec6818_app 即可看到新文件)
"""
import sys
import os
import base64
import subprocess

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
MAXW, MAXH = 480, 360          # 照片最大尺寸
VIDW, FPS = 320, 10            # 视频宽/帧率


def write_b64(raw: bytes, out_name: str):
    txt = base64.b64encode(raw).decode("ascii")
    # 每 76 字符折行, SecureCRT ASCII 发送更稳
    lines = [txt[i:i + 76] for i in range(0, len(txt), 76)]
    path = os.path.join(OUT_DIR, out_name)
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("  [OK] %s  (%d bytes raw -> %d bytes b64)"
          % (out_name, len(raw), os.path.getsize(path)))


def pack_photos(files):
    try:
        from PIL import Image
        have_pil = True
    except ImportError:
        have_pil = False
        print("[WARN] 没装 pillow, 将直接原封不动上传 (仅支持 .jpg, "
              "尺寸别超过 480x360)。建议: pip install pillow")

    for i, src in enumerate(files, start=1):
        if i > 8:
            print("  [SKIP] 最多 8 张照片"); break
        if not os.path.isfile(src):
            print("  [SKIP] 文件不存在: %s" % src); continue
        if have_pil:
            from PIL import Image
            im = Image.open(src).convert("RGB")
            im.thumbnail((MAXW, MAXH), Image.LANCZOS)
            import io
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            raw = buf.getvalue()
            print("  %s -> %dx%d JPEG" % (src, im.width, im.height))
        else:
            if not src.lower().endswith((".jpg", ".jpeg")):
                print("  [SKIP] %s 不是 jpg 且没装 pillow 无法转换" % src); continue
            raw = open(src, "rb").read()
        write_b64(raw, "p%d_b64.txt" % i)


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        for cand in ("ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe"):
            try:
                subprocess.run([cand, "-version"], capture_output=True)
                return cand
            except Exception:
                pass
    return None


def pack_videos(files):
    ff = find_ffmpeg()
    if not ff:
        print("[ERROR] 没找到 ffmpeg。请先安装: pip install imageio-ffmpeg")
        return
    for i, src in enumerate(files, start=1):
        if i > 2:
            print("  [SKIP] 最多 2 个视频"); break
        if not os.path.isfile(src):
            print("  [SKIP] 文件不存在: %s" % src); continue
        tmp = os.path.join(OUT_DIR, "v%d.mjpeg" % i)
        cmd = [
            ff, "-y", "-i", src,
            "-vf", "scale=%d:-2,fps=%d" % (VIDW, FPS),
            "-q:v", "8", "-an", "-f", "mjpeg", tmp,
        ]
        print("  converting %s ..." % src)
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not os.path.isfile(tmp):
            print("  [FAIL] ffmpeg 转换失败:\n" +
                  r.stderr.decode("utf-8", "ignore")[-600:])
            continue
        raw = open(tmp, "rb").read()
        os.remove(tmp)
        write_b64(raw, "v%d_b64.txt" % i)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("photo", "video"):
        print(__doc__)
        sys.exit(1)
    kind, files = sys.argv[1], sys.argv[2:]
    if kind == "photo":
        pack_photos(files)
    else:
        pack_videos(files)
    print("Done. 输出文件在: %s" % OUT_DIR)


if __name__ == "__main__":
    main()
