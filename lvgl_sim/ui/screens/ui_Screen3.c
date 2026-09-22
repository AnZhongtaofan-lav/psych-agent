/* ============================================================
  Screen 3：摄像头预览 + 拍照 + 录像
  粤嵌 GEC6818  LVGL v9.1.0 | 1024×600
  
  布局：
    ┌──────────────────────────────────────────┐
    │  [← 返回]    摄像头预览    [📷拍照][⏺录像] │
    │                                          │
    │        LVGL Canvas（摄像头画面）          │
    │        640 × 480                          │
    │                                          │
    │  状态: Ready / Recording...              │
    └──────────────────────────────────────────┘
  
  Windows 模拟器：Canvas 里画动态色块模拟摄像头画面
  GEC6818 板子：替换成 V4L2 (USB Camera) 帧数据
  ============================================================ */

#include "../ui.h"
#include <string.h>
#include <stdio.h>

/* Canvas buffer（RGB565，GEC6818 黑色边框屏 16bit）*/
#define CAM_W   640
#define CAM_H   480
static uint16_t cam_buf[CAM_W * CAM_H];

/* 状态变量 */
static bool cam_recording = false;
static uint32_t cam_frame_count = 0;
static lv_timer_t * cam_sim_timer = NULL;

/* Canvas 对象（全局，方便事件回调访问）*/
lv_obj_t * ui_Screen3;
lv_obj_t * ui_CameraCanvas;
lv_obj_t * ui_BtnBack;
lv_obj_t * ui_BtnCapture;
lv_obj_t * ui_BtnRecord;
lv_obj_t * ui_StatusLabel;
lv_obj_t * ui_FpsLabel;
lv_obj_t * ui_RecordingLed;   /* 录像红点 */

/* -----------------------------------------------------------
 * 模拟摄像头画面（Windows 模拟器 / 板子上没摄像头时）
 * 一个缓慢移动的彩色方块 + 网格背景
 * 板子上有真实摄像头时用 V4L2 read() 替换此函数
 * ----------------------------------------------------------- */
static void cam_render_sim_frame(void)
{
    static int offset = 0;
    offset = (offset + 2) % CAM_W;

    for (int y = 0; y < CAM_H; y++) {
        for (int x = 0; x < CAM_W; x++) {
            /* 背景：浅灰网格 */
            uint16_t color = (x / 20 + y / 20) % 2 ? 0x867F : 0xC618;
            
            /* 移动的彩色方块（模拟摄像头里的物体）*/
            int cx = CAM_W / 2 + offset - CAM_W / 2;
            if (x >= cx && x < cx + 120 && y >= 140 && y < 340) {
                color = 0xF800;   /* 红色 */
            }
            if (x >= cx + 160 && x < cx + 260 && y >= 140 && y < 340) {
                color = 0x07E0;   /* 绿色 */
            }
            if (x >= cx + 300 && x < cx + 400 && y >= 140 && y < 340) {
                color = 0x001F;   /* 蓝色 */
            }
            /* 中间的时间戳 */
            cam_buf[y * CAM_W + x] = color;
        }
    }
    cam_frame_count++;
}

/* Canvas 刷新 timer —— 30 FPS */
static void cam_timer_cb(lv_timer_t * t)
{
    cam_render_sim_frame();
    lv_canvas_set_buffer(ui_CameraCanvas, cam_buf, CAM_W, CAM_H, LV_IMG_CF_RGB565);

    /* FPS 显示（每 30 帧更一次）*/
    if (cam_frame_count % 30 == 0) {
        static uint32_t last_fps = 0;
        char buf[64];
        lv_snprintf(buf, sizeof(buf), "FPS: ~30  Frame: %u", cam_frame_count);
        lv_label_set_text(ui_FpsLabel, buf);
    }
}

/* -----------------------------------------------------------
 * 按钮事件
 * ----------------------------------------------------------- */
/* 2 秒后恢复状态文字 */
static void cam_status_reset_cb(lv_timer_t * t)
{
    lv_label_set_text(ui_StatusLabel, "Ready — click Capture to take a photo");
    lv_timer_delete(t);
}

void ui_event_BtnCapture(lv_event_t * e)
{
    (void)e;
    static uint32_t shot_count = 0;
    shot_count++;

    /* 模拟保存照片（板子上会写 SD 卡）*/
    char status[128];
    lv_snprintf(status, sizeof(status), "📸 Photo saved! (#%u)", shot_count);
    lv_label_set_text(ui_StatusLabel, status);

    printf("[Camera] Photo captured! #%u\n", shot_count);

    /* 恢复 Ready 文字（2 秒后）*/
    lv_timer_create(cam_status_reset_cb, 2000, NULL);
}

void ui_event_BtnRecord(lv_event_t * e)
{
    (void)e;
    cam_recording = !cam_recording;

    if (cam_recording) {
        lv_label_set_text(ui_StatusLabel, "⏺ Recording...");
        lv_obj_add_state(ui_BtnRecord, LV_STATE_CHECKED);
        lv_obj_remove_flag(ui_RecordingLed, LV_OBJ_FLAG_HIDDEN);   /* 显示红点 */
        printf("[Camera] Recording START\n");
    } else {
        lv_label_set_text(ui_StatusLabel, "⏹ Recording stopped");
        lv_obj_remove_state(ui_BtnRecord, LV_STATE_CHECKED);
        lv_obj_add_flag(ui_RecordingLed, LV_OBJ_FLAG_HIDDEN);      /* 隐藏红点 */
        printf("[Camera] Recording STOPPED\n");
    }
}

void ui_event_BtnBack(lv_event_t * e)
{
    _ui_screen_change(&ui_Screen1, LV_SCR_LOAD_ANIM_MOVE_LEFT, 300, 0, &ui_Screen1_screen_init);
}

/* -----------------------------------------------------------
 * Screen 3 初始化
 * ----------------------------------------------------------- */
void ui_Screen3_screen_init(void)
{
    ui_Screen3 = lv_obj_create(NULL);
    lv_obj_remove_flag(ui_Screen3, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(ui_Screen3, lv_color_hex(0x1A1A2E), 0);   /* 深蓝黑背景 */

    /* === 顶部返回按钮 === */
    ui_BtnBack = lv_button_create(ui_Screen3);
    lv_obj_set_size(ui_BtnBack, 100, 44);
    lv_obj_set_pos(ui_BtnBack, 20, 16);
    lv_obj_set_style_bg_color(ui_BtnBack, lv_color_hex(0xE94560), 0);
    lv_obj_set_style_radius(ui_BtnBack, 8, 0);
    lv_obj_t * lbl = lv_label_create(ui_BtnBack);
    lv_label_set_text(lbl, "← Back");
    lv_obj_center(lbl);
    lv_obj_add_event_cb(ui_BtnBack, ui_event_BtnBack, LV_EVENT_CLICKED, NULL);

    /* === 页面标题 === */
    lv_obj_t * title = lv_label_create(ui_Screen3);
    lv_label_set_text(title, "📷  Camera Preview");
    lv_obj_set_style_text_color(title, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_22, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 22);

    /* === 摄像头 Canvas === */
    ui_CameraCanvas = lv_canvas_create(ui_Screen3);
    lv_canvas_set_buffer(ui_CameraCanvas, cam_buf, CAM_W, CAM_H, LV_IMG_CF_RGB565);
    lv_obj_align(ui_CameraCanvas, LV_ALIGN_CENTER, 0, 20);
    lv_obj_set_style_border_width(ui_CameraCanvas, 2, 0);
    lv_obj_set_style_border_color(ui_CameraCanvas, lv_color_hex(0xE94560), 0);
    lv_obj_set_style_radius(ui_CameraCanvas, 6, 0);

    /* === 拍照按钮 === */
    ui_BtnCapture = lv_button_create(ui_Screen3);
    lv_obj_set_size(ui_BtnCapture, 140, 54);
    lv_obj_align_to(ui_BtnCapture, ui_CameraCanvas, LV_ALIGN_OUT_BOTTOM_LEFT, 0, 20);
    lv_obj_set_style_bg_color(ui_BtnCapture, lv_color_hex(0x0F3460), 0);
    lv_obj_set_style_bg_opa(ui_BtnCapture, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(ui_BtnCapture, 27, 0);   /* 圆按钮 */
    lv_obj_t * lbl_cap = lv_label_create(ui_BtnCapture);
    lv_label_set_text(lbl_cap, "📷 Capture");
    lv_obj_center(lbl_cap);
    lv_obj_add_event_cb(ui_BtnCapture, ui_event_BtnCapture, LV_EVENT_CLICKED, NULL);

    /* === 录像按钮 === */
    ui_BtnRecord = lv_button_create(ui_Screen3);
    lv_obj_set_size(ui_BtnRecord, 140, 54);
    lv_obj_align_to(ui_BtnRecord, ui_CameraCanvas, LV_ALIGN_OUT_BOTTOM_RIGHT, 0, 20);
    lv_obj_set_style_bg_color(ui_BtnRecord, lv_color_hex(0x16213E), 0);
    lv_obj_set_style_radius(ui_BtnRecord, 27, 0);
    lv_obj_t * lbl_rec = lv_label_create(ui_BtnRecord);
    lv_label_set_text(lbl_rec, "⏺ Record");
    lv_obj_center(lbl_rec);
    lv_obj_add_event_cb(ui_BtnRecord, ui_event_BtnRecord, LV_EVENT_CLICKED, NULL);

    /* === 录像小红点（默认隐藏）=== */
    ui_RecordingLed = lv_obj_create(ui_Screen3);
    lv_obj_set_size(ui_RecordingLed, 22, 22);
    lv_obj_set_style_bg_color(ui_RecordingLed, lv_color_hex(0xFF0000), 0);
    lv_obj_set_style_radius(ui_RecordingLed, LV_RADIUS_CIRCLE, 0);
    lv_obj_align_to(ui_RecordingLed, ui_BtnRecord, LV_ALIGN_OUT_TOP_MID, 0, -10);
    lv_obj_add_flag(ui_RecordingLed, LV_OBJ_FLAG_HIDDEN);

    /* === 状态标签 === */
    ui_StatusLabel = lv_label_create(ui_Screen3);
    lv_label_set_text(ui_StatusLabel, "Ready — click Capture to take a photo");
    lv_obj_set_style_text_color(ui_StatusLabel, lv_color_hex(0xAAAAAA), 0);
    lv_obj_align_to(ui_StatusLabel, ui_CameraCanvas, LV_ALIGN_OUT_TOP_LEFT, 0, -10);

    /* === FPS 标签 === */
    ui_FpsLabel = lv_label_create(ui_Screen3);
    lv_label_set_text(ui_FpsLabel, "Initializing...");
    lv_obj_set_style_text_color(ui_FpsLabel, lv_color_hex(0xE94560), 0);
    lv_obj_align_to(ui_FpsLabel, ui_StatusLabel, LV_ALIGN_OUT_RIGHT_MID, 10, 0);

    /* === 启动 Canvas 刷新 timer（30 FPS）=== */
    cam_sim_timer = lv_timer_create(cam_timer_cb, 33, NULL);   /* 1000/30 ≈ 33ms */

    printf("[UI] Screen 3 (Camera) initialized\n");
}
