#!/bin/bash
# ============================================================
# transfer_and_run.sh — 把 gec6818_app 通过 base64 ASCII 传到板子
#
# 前置: SecureCRT 已连上 COM8 (115200 8N1), 登录 root.
#
# 用法:
#   1) 在 Windows PowerShell / msys2 终端跑:
#        bash prep_transfer.sh
#      (生成 gec6818_app.stripped + gec6818_app.b64)
#   2) 在 SecureCRT 板子 shell 里跑:
#        busybox cat > /tmp/gec6818_app.b64
#      然后菜单: Transfer → Send ASCII file → 选 gec6818_app.b64
#      传完后板子端按 Ctrl+C 停 cat
#   3) 板子端跑:
#        busybox base64 -d /tmp/gec6818_app.b64 > /tmp/gec6818_app
#        chmod +x /tmp/gec6818_app
#        /tmp/gec6818_app
# ============================================================
set -e
cd "$(dirname "$0")"

# 1. 编译
bash build_board.sh

# 2. strip
/ucrt64/bin/arm-none-eabi-strip.exe -s gec6818_app -o gec6818_app.stripped
ls -lh gec6818_app.stripped

# 3. base64 编码 (不加 certutil 头尾)
base64 gec6818_app.stripped > gec6818_app.b64
ls -lh gec6818_app.b64
echo ""
echo "========================================"
echo "  Ready to transfer via SecureCRT:"
echo "    1. Board side: busybox cat > /tmp/gec6818_app.b64"
echo "    2. SecureCRT: Transfer → Send ASCII file → gec6818_app.b64"
echo "    3. Board Ctrl+C, then:"
echo "       busybox base64 -d /tmp/gec6818_app.b64 > /tmp/gec6818_app"
echo "       chmod +x /tmp/gec6818_app"
echo "       /tmp/gec6818_app"
echo "========================================"
