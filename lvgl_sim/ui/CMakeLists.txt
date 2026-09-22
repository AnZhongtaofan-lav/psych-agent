SET(SOURCES screens/ui_Screen1.c
    screens/ui_Screen2.c
    screens/ui_Screen3.c        # ✅ 新增：摄像头预览 Screen
    ui.c
    components/ui_comp_hook.c
    ui_helpers.c
    ui_events.c)

add_library(ui ${SOURCES})

# ✅ 关键！让 ui 能找到 lvgl/lvgl.h 和 ui/ui.h
target_include_directories(ui PUBLIC ${PROJECT_SOURCE_DIR})
