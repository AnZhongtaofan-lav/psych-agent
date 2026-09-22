#!/bin/bash
# 快速重建: 只重编改动的文件 + 重新链接, 不重编 211 个 LVGL 文件
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
set -e
OBJDIR=./build_board_obj
CFLAGS="-O2 -fno-builtin -Wall -Wno-unused-function -Wno-unused-variable -Wno-format \
        -DLV_USE_LIBPNG=0 -DLV_USE_LIBJPEG_TURBO=0 -DLV_USE_FREETYPE=0 \
        -DLV_USE_TINY_TTF=0 -DLV_USE_BMP=0 -DLV_USE_GIF=0 -DLV_USE_QRCODE=0 \
        -DLV_USE_LODEPNG=0 -DLV_USE_THORVG=0 -DLV_USE_LZ4=0 -DLV_USE_RLE=0 \
        -DLV_USE_FS_POSIX=0 -DLV_USE_FS_STDIO=0 -DLV_USE_FS_WIN32=0 \
        -I. -Ilvgl -Ilvgl/src"
LDFLAGS="-e _start -nostdlib -nostartfiles -static -Wl,--gc-sections -lgcc"

for f in "$@"; do
  echo "[fast] recompiling $f"
  arm-none-eabi-gcc $CFLAGS -c "$f" -o "$OBJDIR/$(basename $f .c).o"
done

OBJS="$OBJDIR/syscalls.o $OBJDIR/main_board.o $(ls $OBJDIR/*.o | grep -v -E 'syscalls|main_board')"
arm-none-eabi-gcc $OBJS $LDFLAGS -o gec6818_app
arm-none-eabi-strip -s gec6818_app -o gec6818_app.stripped
base64 gec6818_app.stripped > gec6818_app_b64.txt
cp gec6818_app_b64.txt gec6818_app.b64
echo "FASTBUILD_DONE size=$(stat -c%s gec6818_app.stripped) b64=$(stat -c%s gec6818_app_b64.txt)"
