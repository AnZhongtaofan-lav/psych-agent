# ============================================================
#  LVGL SDL 模拟器 — Windows 编译配置
#  编译后会得到一个 exe，弹出 GEC6818 模拟触摸屏窗口
#
#  编译命令（MSYS2 MinGW64 环境）：
#    cmake -B build_sim -G "MinGW Makefiles"
#    cmake --build build_sim -j8
#    .\build_sim\main.exe
#
#  或者用 MSYS2 bash：
#    cd /d/psych-architect/psych/lvgl_sim
#    cmake -B build_sim -G "MinGW Makefiles"
#    cmake --build build_sim -j8
#    ./build_sim/main.exe
# ============================================================

cmake_minimum_required(VERSION 3.14)
project(gec6818_lvgl_sim LANGUAGES C CXX)   # ← CXX 必须加！thorvg 是 C++

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# LVGL 主库
add_subdirectory(lvgl)
target_include_directories(lvgl PUBLIC ${PROJECT_SOURCE_DIR})

# ✅ 不再依赖 ui/ 目录 —— main_sim.c 直接用 LVGL API 创建界面
# add_subdirectory(ui)

# 可执行文件（用 main_sim.c 而不是 main.c）
add_executable(main
    main_sim.c               # Windows SDL 模拟器入口（直接创建 LVGL UI）
)

# 让 LVGL 的 examples/demos 也链接进来
# thorvg 在 lv_conf.h 里关掉了（INTERNAL=0, EXTERNAL=0），所以不链接
target_link_libraries(main PRIVATE
    lvgl
    lvgl::examples
    lvgl::demos
)

# ============
# SDL2（Windows 版）
# ============
# 方式 1：MSYS2 MinGW64（推荐，pacman 装的包）
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(SDL2 REQUIRED sdl2)
    pkg_check_modules(SDL2_IMAGE QUIET SDL2_image)
    target_include_directories(main PRIVATE ${SDL2_INCLUDE_DIRS} ${SDL2_IMAGE_INCLUDE_DIRS})
    target_link_libraries(main PRIVATE ${SDL2_LIBRARIES} ${SDL2_IMAGE_LIBRARIES})
    message(STATUS "✓ 通过 pkg-config 找到 SDL2: ${SDL2_VERSION}")
else()
    message(FATAL_ERROR "没找到 pkg-config —— 请先装 MSYS2 或 vcpkg")
endif()

# ============
# 编译选项
# ============
target_compile_definitions(main PRIVATE
    LV_USE_SDL=1              # 启用 SDL 模拟器
    LV_USE_LINUX_FBDEV=0      # 关掉 fbdev（Windows 没有 /dev/fb0）
    LV_USE_EVDEV=0            # 关掉 evdev（Windows 没有 /dev/input/event0）
)

# ✅ SDL_MAIN_HANDLED 已在 main_sim.c 顶部 #define，避免重复定义

message(STATUS "")
message(STATUS "========================================")
message(STATUS "  LVGL SDL 模拟器 Windows 构建配置完成")
message(STATUS "  目标: main.exe (1024x600, GEC6818)")
message(STATUS "========================================")
message(STATUS "")
