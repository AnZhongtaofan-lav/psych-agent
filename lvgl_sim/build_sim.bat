@echo off
REM ============================================================
REM  一键编译 LVGL SDL 模拟器 (Windows)
REM  运行: 双击本文件 或 在 PowerShell/bash 里执行
REM  输出: lvgl_sim\build_sim\main.exe
REM ============================================================

setlocal
cd /d "%~dp0"

echo ============================================================
echo  编译 LVGL SDL 模拟器 ...
echo.

REM 备份原有 CMakeLists.txt（板子编译时恢复）
if not exist "CMakeLists_backup.txt" (
    copy CMakeLists.txt CMakeLists_backup.txt >nul
    echo [备份] CMakeLists.txt -^> CMakeLists_backup.txt
)

REM 用 SDL 版替换
copy /Y CMakeLists_sim.txt CMakeLists.txt >nul

REM 清理旧构建
if exist "build_sim" rmdir /s /q build_sim

REM CMake 配置（用 MinGW Makefiles）
echo.
echo [1/2] CMake 配置 ...
cmake -B build_sim -G "MinGW Makefiles"
if errorlevel 1 (
    echo.
    echo [ERROR] CMake 配置失败！
    echo  可能原因:
    echo   1. MSYS2 SDL2 没装 —— 运行: D:\msys64\usr\bin\bash.exe -c "pacman -S mingw-w64-x86_64-SDL2 mingw-w64-x86_64-SDL2_image"
    echo   2. MinGW 不在 PATH —— 把 D:\msys64\mingw64\bin 加到系统 PATH
    echo.
    goto :restore
)

REM 编译
echo.
echo [2/2] 编译 ...
cmake --build build_sim -j%NUMBER_OF_PROCESSORS%
if errorlevel 1 (
    echo.
    echo [ERROR] 编译失败！往上滚动看具体错误信息
    echo.
    goto :restore
)

echo.
echo ============================================================
echo  ✓ 编译成功！
echo  可执行文件: %~dp0build_sim\main.exe
echo.
echo  运行方式: 双击 build_sim\main.exe
echo  或者: 命令行执行 build_sim\main.exe
echo ============================================================

:restore
REM 恢复原有 CMakeLists.txt（给板子编译用）
if exist "CMakeLists_backup.txt" (
    copy /Y CMakeLists_backup.txt CMakeLists.txt >nul
    echo.
    echo [恢复] CMakeLists_backup.txt -^> CMakeLists.txt
)

endlocal
pause
