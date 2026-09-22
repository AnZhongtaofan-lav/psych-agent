#!/bin/bash
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
arm-none-eabi-gcc -O2 -fno-builtin -I. -e _start -nostdlib -nostartfiles -static \
    syscalls.c cam_scan.c -lgcc -o cam_scan 2>cs_err.txt
echo "gcc=$?"; head -20 cs_err.txt
arm-none-eabi-strip -s cam_scan -o cam_scan.stripped
base64 cam_scan.stripped > cam_scan_b64.txt
stat -c '%s %n' cam_scan.stripped cam_scan_b64.txt
