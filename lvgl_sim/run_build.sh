#!/bin/bash
set -e
cd /d/psych-architect/psych/lvgl_sim

echo "[备份] CMakeLists.txt -> CMakeLists_backup.txt"
cp -f CMakeLists.txt CMakeLists_backup.txt

echo "[替换] CMakeLists_sim.txt -> CMakeLists.txt"
cp -f CMakeLists_sim.txt CMakeLists.txt

echo ""
echo "======= CMake 配置 ======="
rm -rf build_sim
cmake -B build_sim -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release 2>&1

echo ""
echo "======= 编译 ======="
cmake --build build_sim -j$(nproc) 2>&1

echo ""
echo "======= 恢复 CMakeLists.txt ======="
cp -f CMakeLists_backup.txt CMakeLists.txt

echo ""
echo "✓ 编译完成！可执行文件: build_sim/main.exe"
ls -lh build_sim/main.exe 2>/dev/null
