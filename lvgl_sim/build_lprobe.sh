#!/bin/bash
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
rm -f fb_lprobe fb_lprobe.stripped fb_lprobe_b64.txt
arm-none-eabi-gcc -O2 -fno-builtin -I. -e _start -nostdlib -nostartfiles -static \
    syscalls.c fb_lprobe.c -lgcc -o fb_lprobe
echo "gcc=$?"
ls -l fb_lprobe
arm-none-eabi-strip -s fb_lprobe -o fb_lprobe.stripped
base64 fb_lprobe.stripped > fb_lprobe_b64.txt
stat -c '%s %n' fb_lprobe.stripped fb_lprobe_b64.txt
