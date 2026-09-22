#!/bin/bash
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
# 只看非 LVGL、非编译器内部的未定义符号 = 我们要在 syscalls.c 补的 libc 函数
arm-none-eabi-nm build_board_obj/*.o | grep ' U ' | awk '{print $2}' | sort -u | \
  grep -v -E '^(lv_|_lv_|__aeabi|__gnu|__cxa|_GLOBAL|main$|g_ui|g_screens)'
