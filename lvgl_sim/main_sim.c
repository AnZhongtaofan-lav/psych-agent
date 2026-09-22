/* ============================================================
  LVGL SDL 模拟器 —— 心理 AI 摄像头终端（Windows 版）
  屏幕: 1024×600 | GEC6818 | LVGL v9.1.0 | SDL 模拟器
  
  三个 Screen：
    Screen1 (Chat):       AI chat + input + send
    Screen2 (Camera):     Canvas preview + capture/record buttons
    Screen3 (Gallery):    Photo & video thumbnails grid

  Board porting:
    - Replace main_sim.c with main.c (fbdev+evdev)
    - Keep all create_screen_xxx() functions
    - board main.c calls lv_scr_load() same way

  操作：
    鼠标左键 = 触摸屏点击
    鼠标移动 = 触摸滑动
    点底部导航栏切换三个页面
  ============================================================ */

#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

#include "lvgl/lvgl.h"
#include "lvgl/src/drivers/sdl/lv_sdl_window.h"
#include "lvgl/src/drivers/sdl/lv_sdl_mouse.h"
#include "lvgl/src/drivers/sdl/lv_sdl_keyboard.h"
#include <stdio.h>
#include <string.h>

/* Screen resolution (GEC6818: 1024x600) */
#define SCREEN_W   1024
#define SCREEN_H    600

/* Three screens */
static lv_obj_t *g_screen_chat;
static lv_obj_t *g_screen_camera;
static lv_obj_t *g_screen_gallery;

/* Camera page refs */
static lv_obj_t *g_cam_canvas;
static lv_obj_t *g_cam_label_status;
static bool      g_recording = false;

/* Sim camera frame (640x480 RGB565) */
#define CAM_W 640
#define CAM_H 480
static lv_color16_t g_cam_frame[CAM_W * CAM_H];

/* ------------------------------------------------------------
 * Sim camera frame generator (rainbow + moving blocks)
 * On real board: replace with DCMI/V4L2 frame capture
 * ------------------------------------------------------------ */
static uint32_t g_frame_counter = 0;

static inline uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b)
{
    return ((uint16_t)(r & 0xF8) << 8) | ((uint16_t)(g & 0xFC) << 3) | (b >> 3);
}

static void cam_sim_update(void)
{
    g_frame_counter++;
    uint32_t phase = g_frame_counter % 360;
    
    for (int y = 0; y < CAM_H; y++) {
        for (int x = 0; x < CAM_W; x++) {
            uint8_t r, g, b;
            r = (uint8_t)((x * 255 / CAM_W + phase * 2) & 0xFF);
            g = (uint8_t)((y * 255 / CAM_H + phase) & 0xFF);
            b = (uint8_t)(((x + y) * 255 / (CAM_W + CAM_H) + phase * 3) & 0xFF);
            int bx = (g_frame_counter * 2) % (CAM_W - 80);
            int by = (g_frame_counter * 3) % (CAM_H - 80);
            if (x >= bx && x < bx + 80 && y >= by && y < by + 80) {
                r = 255; g = 0; b = 0;
            }
            int bx2 = CAM_W - 100 - (g_frame_counter * 3) % (CAM_W - 120);
            int by2 = CAM_H - 100 - (g_frame_counter * 2) % (CAM_H - 120);
            if (x >= bx2 && x < bx2 + 60 && y >= by2 && y < by2 + 60) {
                r = 0; g = 0; b = 255;
            }
            uint16_t v = rgb565(r, g, b);
            g_cam_frame[y * CAM_W + x].red   = (uint16_t)(v >> 11);
            g_cam_frame[y * CAM_W + x].green = (uint16_t)((v >> 5) & 0x3F);
            g_cam_frame[y * CAM_W + x].blue  = (uint16_t)(v & 0x1F);
        }
    }
}

static void cam_canvas_timer_cb(lv_timer_t *timer)
{
    LV_UNUSED(timer);
    cam_sim_update();
    lv_canvas_set_buffer(g_cam_canvas, g_cam_frame, CAM_W, CAM_H, LV_COLOR_FORMAT_RGB565);
    lv_obj_invalidate(g_cam_canvas);
}

/* Camera button events */
static void btn_capture_cb(lv_event_t *e)
{
    LV_UNUSED(e);
    lv_label_set_text(g_cam_label_status, "Photo saved -> media/photos/");
    printf("[CAM] Photo captured -> media/photos/photo_%04u.jpg\n", (unsigned)g_frame_counter);
}

static void btn_record_cb(lv_event_t *e)
{
    g_recording = !g_recording;
    lv_obj_t *btn = lv_event_get_target(e);
    lv_obj_t *lbl = lv_obj_get_child(btn, 0);
    if (g_recording) {
        lv_label_set_text(g_cam_label_status, "RECORDING... click to stop");
        lv_label_set_text(lbl, "STOP");
        printf("[CAM] Recording STARTED\n");
    } else {
        lv_label_set_text(g_cam_label_status, "Video saved -> media/videos/");
        lv_label_set_text(lbl, "REC");
        printf("[CAM] Recording STOPPED -> media/videos/video_%04u.mp4\n", (unsigned)g_frame_counter);
    }
}

/* Navigation bar */
static void nav_goto_chat(lv_event_t *e)     { lv_scr_load(g_screen_chat); }
static void nav_goto_camera(lv_event_t *e)   { lv_scr_load(g_screen_camera); }
static void nav_goto_gallery(lv_event_t *e)  { lv_scr_load(g_screen_gallery); }

static void create_nav_bar(lv_obj_t *parent)
{
    lv_obj_t *bar = lv_obj_create(parent);
    lv_obj_set_size(bar, SCREEN_W, 60);
    lv_obj_align(bar, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(0x1a1a2e), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_pad_all(bar, 0, 0);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);

    struct { const char *txt; lv_event_cb_t cb; } tabs[] = {
        {"CHAT", nav_goto_chat},
        {"CAM", nav_goto_camera},
        {"PHOTOS", nav_goto_gallery},
    };
    for (int i = 0; i < 3; i++) {
        lv_obj_t *btn = lv_btn_create(bar);
        lv_obj_set_size(btn, SCREEN_W / 3 - 4, 52);
        lv_obj_align(btn, LV_ALIGN_CENTER, (i - 1) * (SCREEN_W / 3), 0);
        lv_obj_set_style_bg_color(btn, lv_color_hex(0x16213e), 0);
        lv_obj_set_style_bg_opa(btn, LV_OPA_COVER, 0);
        lv_obj_set_style_radius(btn, 8, 0);
        lv_obj_add_event_cb(btn, tabs[i].cb, LV_EVENT_CLICKED, NULL);
        lv_obj_t *label = lv_label_create(btn);
        lv_obj_center(label);
        lv_label_set_text(label, tabs[i].txt);
        lv_obj_set_style_text_color(label, lv_color_white(), 0);
    }
}

/* ============================================================
 * Screen 1: Chat
 * ============================================================ */
static void create_screen_chat(void)
{
    g_screen_chat = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(g_screen_chat, lv_color_hex(0x0f0f23), 0);
    lv_obj_set_style_bg_opa(g_screen_chat, LV_OPA_COVER, 0);

    lv_obj_t *title = lv_label_create(g_screen_chat);
    lv_label_set_text(title, "Psych AI Assistant");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 15);

    lv_obj_t *msg_area = lv_obj_create(g_screen_chat);
    lv_obj_set_size(msg_area, SCREEN_W - 40, SCREEN_H - 200);
    lv_obj_align(msg_area, LV_ALIGN_TOP_MID, 0, 70);
    lv_obj_set_style_bg_color(msg_area, lv_color_hex(0x1a1a2e), 0);
    lv_obj_set_style_bg_opa(msg_area, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(msg_area, 12, 0);
    lv_obj_set_style_border_width(msg_area, 0, 0);
    lv_obj_set_style_pad_all(msg_area, 15, 0);

    lv_obj_t *ai_msg = lv_label_create(msg_area);
    lv_label_set_text(ai_msg, "Hello! I'm your Psych AI assistant.\nHow are you feeling today?");
    lv_obj_set_style_text_color(ai_msg, lv_color_hex(0x88d8ff), 0);
    lv_obj_set_style_text_font(ai_msg, &lv_font_montserrat_14, 0);
    lv_label_set_long_mode(ai_msg, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(ai_msg, SCREEN_W - 80);

    lv_obj_t *ta = lv_textarea_create(g_screen_chat);
    lv_obj_set_size(ta, SCREEN_W - 200, 50);
    lv_obj_align(ta, LV_ALIGN_BOTTOM_MID, -80, -75);
    lv_textarea_set_placeholder_text(ta, "Type here...");
    lv_obj_set_style_bg_color(ta, lv_color_hex(0x1a1a2e), 0);
    lv_obj_set_style_text_color(ta, lv_color_white(), 0);
    lv_obj_set_style_border_color(ta, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_border_width(ta, 2, 0);

    lv_obj_t *send_btn = lv_btn_create(g_screen_chat);
    lv_obj_set_size(send_btn, 150, 50);
    lv_obj_align(send_btn, LV_ALIGN_BOTTOM_MID, 80, -75);
    lv_obj_set_style_bg_color(send_btn, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_bg_opa(send_btn, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(send_btn, 10, 0);
    lv_obj_t *send_lbl = lv_label_create(send_btn);
    lv_label_set_text(send_lbl, "SEND >");
    lv_obj_center(send_lbl);
    lv_obj_set_style_text_color(send_lbl, lv_color_black(), 0);

    create_nav_bar(g_screen_chat);
}

/* ============================================================
 * Screen 2: Camera
 * ============================================================ */
static void create_screen_camera(void)
{
    g_screen_camera = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(g_screen_camera, lv_color_hex(0x0f0f23), 0);
    lv_obj_set_style_bg_opa(g_screen_camera, LV_OPA_COVER, 0);

    lv_obj_t *title = lv_label_create(g_screen_camera);
    lv_label_set_text(title, "Camera Preview");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 10);

    g_cam_canvas = lv_canvas_create(g_screen_camera);
    lv_obj_set_size(g_cam_canvas, CAM_W, CAM_H);
    lv_obj_align(g_cam_canvas, LV_ALIGN_TOP_MID, 0, 50);
    lv_obj_set_style_bg_color(g_cam_canvas, lv_color_black(), 0);
    lv_obj_set_style_border_width(g_cam_canvas, 2, 0);
    lv_obj_set_style_border_color(g_cam_canvas, lv_color_hex(0x00d9ff), 0);

    lv_obj_t *cap_btn = lv_btn_create(g_screen_camera);
    lv_obj_set_size(cap_btn, 120, 55);
    lv_obj_align(cap_btn, LV_ALIGN_TOP_MID, -200, 545);
    lv_obj_set_style_bg_color(cap_btn, lv_color_hex(0xff4757), 0);
    lv_obj_set_style_bg_opa(cap_btn, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(cap_btn, 27, 0);
    lv_obj_add_event_cb(cap_btn, btn_capture_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *cap_lbl = lv_label_create(cap_btn);
    lv_label_set_text(cap_lbl, "CAPTURE");
    lv_obj_center(cap_lbl);
    lv_obj_set_style_text_color(cap_lbl, lv_color_white(), 0);
    lv_obj_set_style_text_font(cap_lbl, &lv_font_montserrat_16, 0);

    lv_obj_t *rec_btn = lv_btn_create(g_screen_camera);
    lv_obj_set_size(rec_btn, 160, 55);
    lv_obj_align(rec_btn, LV_ALIGN_TOP_MID, 200, 545);
    lv_obj_set_style_bg_color(rec_btn, lv_color_hex(0x2ed573), 0);
    lv_obj_set_style_bg_opa(rec_btn, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(rec_btn, 27, 0);
    lv_obj_add_event_cb(rec_btn, btn_record_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *rec_lbl = lv_label_create(rec_btn);
    lv_label_set_text(rec_lbl, "REC");
    lv_obj_center(rec_lbl);
    lv_obj_set_style_text_color(rec_lbl, lv_color_white(), 0);
    lv_obj_set_style_text_font(rec_lbl, &lv_font_montserrat_16, 0);

    g_cam_label_status = lv_label_create(g_screen_camera);
    lv_label_set_text(g_cam_label_status, "Ready - click CAPTURE or REC");
    lv_obj_set_style_text_color(g_cam_label_status, lv_color_hex(0x2ed573), 0);
    lv_obj_set_style_text_font(g_cam_label_status, &lv_font_montserrat_14, 0);
    lv_obj_align(g_cam_label_status, LV_ALIGN_TOP_MID, 0, 530);

    lv_timer_create(cam_canvas_timer_cb, 33, NULL);
    create_nav_bar(g_screen_camera);
}

/* ============================================================
 * Screen 3: Gallery
 * ============================================================ */
static void create_screen_gallery(void)
{
    g_screen_gallery = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(g_screen_gallery, lv_color_hex(0x0f0f23), 0);
    lv_obj_set_style_bg_opa(g_screen_gallery, LV_OPA_COVER, 0);

    lv_obj_t *title = lv_label_create(g_screen_gallery);
    lv_label_set_text(title, "Photos & Videos");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 15);

    lv_obj_t *empty = lv_label_create(g_screen_gallery);
    lv_label_set_text(empty, "No media yet.\nGo to CAM page to capture!");
    lv_obj_set_style_text_color(empty, lv_color_hex(0x888888), 0);
    lv_obj_set_style_text_font(empty, &lv_font_montserrat_16, 0);
    lv_obj_align(empty, LV_ALIGN_CENTER, 0, -20);
    lv_label_set_long_mode(empty, LV_LABEL_LONG_WRAP);

    create_nav_bar(g_screen_gallery);
}

/* ============================================================
 * Main
 * ============================================================ */
int main(int argc, char *argv[])
{
    printf("============================================================\n");
    printf("  LVGL SDL Simulator -- Psych AI Camera Terminal\n");
    printf("  Screen: %dx%d | LVGL v9.1.0 | Mouse = Touch\n", SCREEN_W, SCREEN_H);
    printf("============================================================\n\n");

    lv_init();
    lv_sdl_window_create(SCREEN_W, SCREEN_H);
    lv_sdl_mouse_create();
    lv_sdl_keyboard_create();
    lv_sdl_window_set_title(lv_display_get_default(), "GEC6818 - Psych AI Camera Terminal");

    printf("SDL window %dx%d created\n", SCREEN_W, SCREEN_H);

    create_screen_chat();
    create_screen_camera();
    create_screen_gallery();
    lv_scr_load(g_screen_chat);

    printf("3 screens ready. ESC or close window to quit.\n\n");

    while (1) {
        lv_timer_handler();
        SDL_Delay(5);
    }
    return 0;
}
