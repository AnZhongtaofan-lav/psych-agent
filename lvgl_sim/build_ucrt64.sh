#!/bin/bash
# ============================================================
#  LVGL SDL 模拟器 —— ucrt64 环境一键编译
#  在 ucrt64.exe 终端里运行: bash build_ucrt64.sh
# ============================================================

set -e
cd "$(dirname "$0")"

echo "========================================"
echo "  LVGL GEC6818 模拟器编译"
echo "========================================"

# 备份板子编译用的 CMakeLists.txt
if [ ! -f CMakeLists_backup.txt ]; then
    cp CMakeLists.txt CMakeLists_backup.txt
    echo "[备份] CMakeLists.txt -> CMakeLists_backup.txt"
fi

# 替换成 SDL 模拟器版
cp CMakeLists_sim.txt CMakeLists.txt

# 清理 + 编译
rm -rf build_sim
echo ""
echo "[1/2] CMake 配置 ..."
cmake -B build_sim -G "MinGW Makefiles" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=gcc

echo ""
echo "[2/2] 编译 ..."
cmake --build build_sim -j$(nproc)

echo ""
echo "========================================"
echo "  ✓ 编译成功！"
echo "  运行: ./build_sim/main.exe"
echo "========================================"

# 恢复板子编译用的 CMakeLists.txt
cp CMakeLists_backup.txt CMakeLists.txt
echo "[恢复] CMakeLists_backup.txt -> CMakeLists.txt"
