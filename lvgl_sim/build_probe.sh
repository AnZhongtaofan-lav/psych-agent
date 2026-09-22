#!/bin/bash
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
echo "=== compiling fb_probe ==="
arm-none-eabi-gcc -O2 -fno-builtin -Wall -Wno-format -I. \
    -e _start -nostdlib -nostartfiles -static \
    syscalls.c fb_probe.c -lgcc -o fb_probe
echo "gcc exit=$?"
ls -lh fb_probe 2>&1
arm-none-eabi-strip -s fb_probe -o fb_probe.stripped
base64 fb_probe.stripped > fb_probe_b64.txt
echo "=== result ==="
ls -lh fb_probe.stripped fb_probe_b64.txt
wc -l fb_probe_b64.txt
