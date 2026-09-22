#!/bin/bash
cd /d/psych-architect/psych/lvgl_sim
export PATH=/ucrt64/bin:$PATH
arm-none-eabi-gcc -O2 -fno-builtin -I. -e _start -nostdlib -nostartfiles -static \
    syscalls.c cam_probe.c -lgcc -o cam_probe 2>cp_err.txt
echo "gcc=$?"
head -20 cp_err.txt
arm-none-eabi-strip -s cam_probe -o cam_probe.stripped
base64 cam_probe.stripped > cam_probe_b64.txt
stat -c '%s %n' cam_probe.stripped cam_probe_b64.txt
