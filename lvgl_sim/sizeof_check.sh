#!/bin/bash
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
echo "=== LV_COLOR_DEPTH macro ==="
arm-none-eabi-gcc -O2 -fno-builtin -I. -Ilvgl -Ilvgl/src \
  -dM -E sizeof_test.c | grep -E '^#define (LV_COLOR_DEPTH|LV_DRAW_BUF_STRIDE_ALIGN|LV_DRAW_BUF_ALIGN) '
echo "=== sizeof via compile-time array trick ==="
cat > /tmp/st.c <<'EOF'
#include "lvgl/lvgl.h"
char s_lc[sizeof(lv_color_t)];
char s_need[(int)(800*4*480)];
EOF
arm-none-eabi-gcc -O2 -fno-builtin -I. -Ilvgl -Ilvgl/src -c /tmp/st.c -o /tmp/st.o
arm-none-eabi-nm -S /tmp/st.o | grep -E ' s_(lc|need)'
