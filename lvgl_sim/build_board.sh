#!/bin/bash
# ============================================================
# build_board.sh — 在 mingw64 / ucrt64 终端里跑
#   1. 编 syscalls.c + main_board.c
#   2. 循环编 lvgl/src 下所有 .c (排除不需要的子目录)
#   3. 链接 → gec6818_app
# ============================================================
set -e
cd "$(dirname "$0")"

# 1) 找 arm-none-eabi-gcc
export PATH=/ucrt64/bin:/mingw64/bin:$PATH
CC=arm-none-eabi-gcc
if ! command -v $CC >/dev/null 2>&1; then
    echo "ERROR: $CC not found in PATH. Try: export PATH=/ucrt64/bin:\$PATH"
    exit 1
fi
echo "[CC] $($CC --version | head -1)"

# 2) 准备输出目录
OBJDIR=./build_board_obj
OUT=gec6818_app
rm -rf "$OBJDIR"
mkdir -p "$OBJDIR"

# 3) 公共编译参数
# 注意: 不传 -DLV_CONF_PATH (会让 #include 解析失败), 靠 -I. 让
#       __has_include("lv_conf.h") 找到 d:\...\lvgl_sim\lv_conf.h
# -fno-builtin: 关键! 我们自己实现 memset/memcpy/strlen 等, GCC 默认会把
# 这些函数的函数体"优化"成对同名库函数的调用 -> 无限递归 -> 栈爆段错误.
CFLAGS="-O2 -fno-builtin -Wall -Wno-unused-function -Wno-unused-variable -Wno-format \
        -DLV_USE_LIBPNG=0 -DLV_USE_LIBJPEG_TURBO=0 -DLV_USE_FREETYPE=0 \
        -DLV_USE_TINY_TTF=0 -DLV_USE_BMP=0 -DLV_USE_GIF=0 -DLV_USE_QRCODE=0 \
        -DLV_USE_LODEPNG=0 -DLV_USE_THORVG=0 -DLV_USE_LZ4=0 -DLV_USE_RLE=0 \
        -DLV_USE_FS_POSIX=0 -DLV_USE_FS_STDIO=0 -DLV_USE_FS_WIN32=0 \
        -I. -Ilvgl -Ilvgl/src"

# -nostdlib: 不要 libc (我们有自己的 malloc/printf/syscalls)
# -lgcc: 要 libgcc.a (__aeabi_uidiv / __aeabi_idiv / __aeabi_uidivmod 等 ARM EABI 除法助手)
LDFLAGS="-e _start -nostdlib -nostartfiles -static -Wl,--gc-sections -lgcc"

# 4) 编 syscalls.c 和 main_board.c
echo ""
echo "[1/3] compiling syscalls.c and main_board.c ..."
$CC $CFLAGS -c syscalls.c   -o "$OBJDIR/syscalls.o"
$CC $CFLAGS -c media.c      -o "$OBJDIR/media.o"
$CC $CFLAGS -c main_board.c -o "$OBJDIR/main_board.o"
# TJPGD: 核心解码器 + LVGL 注册封装(lv_init 会调 lv_tjpgd_init)
$CC $CFLAGS -c lvgl/src/libs/tjpgd/tjpgd.c    -o "$OBJDIR/ztjpgd.o"
$CC $CFLAGS -c lvgl/src/libs/tjpgd/lv_tjpgd.c -o "$OBJDIR/zlv_tjpgd.o"

# 5) 找 LVGL 源文件, 排除不需要的子目录
echo "[2/3] compiling LVGL source files ..."
LVGL_SRC=$(find lvgl/src -name '*.c' -type f \
    ! -path '*/libs/freetype/*' \
    ! -path '*/libs/libpng/*' \
    ! -path '*/libs/libjpeg_turbo/*' \
    ! -path '*/libs/thorvg/*' \
    ! -path '*/libs/rlottie/*' \
    ! -path '*/libs/ffmpeg/*' \
    ! -path '*/libs/lodepng/*' \
    ! -path '*/libs/tjpgd/*' \
    ! -path '*/libs/gif/*' \
    ! -path '*/libs/bmp/*' \
    ! -path '*/libs/rle/*' \
    ! -path '*/libs/qrcode/*' \
    ! -path '*/libs/barcode/*' \
    ! -path '*/libs/lz4/*' \
    ! -path '*/libs/tiny_ttf/*' \
    ! -path '*/libs/fsdrv/*' \
    ! -path '*/libs/lv_fs_win32.c' \
    ! -path '*/drivers/sdl/*' \
    ! -path '*/drivers/x11/*' \
    ! -path '*/drivers/libinput/*' \
    ! -path '*/drivers/windows/*' \
    ! -path '*/drivers/nuttx/*' \
    ! -path '*/drivers/display/*' \
    ! -path '*/drivers/evdev/*' \
    ! -path '*/osal/lv_freertos*' \
    ! -path '*/osal/lv_rtthread*' \
    ! -path '*/osal/lv_cmsis*' \
    ! -path '*/osal/lv_pthread*' \
    ! -path '*/osal/lv_windows*' \
    ! -path '*/others/*')

TOTAL=$(echo "$LVGL_SRC" | wc -l)
echo "    total $TOTAL files to compile"

i=0
fail=0
for f in $LVGL_SRC; do
    i=$((i+1))
    # 用 basename + 短 hash 避免重名 (lv_*.c 在不同子目录可能重名)
    base=$(basename "$f" .c)
    out="$OBJDIR/${base}_$(echo "$f" | md5sum | cut -c1-6).o"
    if ! $CC $CFLAGS -c "$f" -o "$out" 2>"$OBJDIR/err_${i}.log"; then
        echo "    [FAIL] $f"
        head -3 "$OBJDIR/err_${i}.log"
        fail=$((fail+1))
        # 不 exit, 继续编其他文件
    fi
    if (( i % 50 == 0 )); then
        echo "    ... $i / $TOTAL"
    fi
done
echo "    compiled $i files, $fail failed"

# 6) 链接
echo ""
echo "[3/3] linking $OUT ..."
OBJS="$OBJDIR/syscalls.o $OBJDIR/main_board.o $(ls $OBJDIR/*.o | grep -v syscalls | grep -v main_board)"
$CC $OBJS $LDFLAGS -o "$OUT" 2>"$OBJDIR/link.log" || {
    echo "[LINK FAILED]"
    head -50 "$OBJDIR/link.log"
    exit 1
}

echo ""
echo "========================================"
echo "  BUILD SUCCESS"
echo "========================================"
ls -lh "$OUT"
echo "  Size: $(stat -c%s "$OUT" 2>/dev/null || wc -c < "$OUT") bytes"
