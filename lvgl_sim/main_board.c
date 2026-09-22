/* ============================================================
 * LVGL GEC6818 board -- Psych AI Terminal
 *
 *   Screen: 800x480 framebuffer /dev/fb0 (BGRX8888 32-bit)
 *   Touch:  evdev /dev/input/event0
 *
 *   页面: CHAT 智能体对话(串口中转到笔记本上的大模型)
 *         PHOTOS 相册(JPEG, TJPGD 软解)
 *         VIDEO  MJPEG 视频播放
 *
 *   媒体文件目录: /tmp/media/
 *     照片 p1.jpg ... p8.jpg
 *     视频 v1.mjpeg ... v2.mjpeg
 *
 *   智能体串口协议(115200):
 *     板子 -> 笔记本 : "@@Q<问题>\n"
 *     笔记本 -> 板子 : "@@A<回答>\n"
 * ============================================================ */

#include "linux_shim.h"
#include "lvgl/lvgl.h"
#include "media.h"

#define SCREEN_W    800
#define SCREEN_H    480
#define FB_DEV      "/dev/fb0"
#define TOUCH_DEV   "/dev/input/event0"
#define MEDIA_DIR   "/tmp/media"

#define MAX_PHOTOS  8
#define MAX_VIDEOS  2
#define THUMB_W     176
#define THUMB_H     132
#define VIEW_W      480
#define VIEW_H      360
#define VID_W       320
#define VID_H       240

/* ----------------------- Framebuffer ----------------------- */
static int          g_fb_fd = -1;
static uint8_t     *g_fb_map = NULL;
static long        g_fb_size = 0;
static struct fb_var_screeninfo g_fb_vinfo;
static lv_display_t *g_display;

static void fbdev_init(void)
{
    g_fb_fd = open(FB_DEV, O_RDWR, 0);
    if (g_fb_fd < 0) { printf("[FB] ERROR: cannot open %s\n", FB_DEV); exit(1); }
    char *p = (char *)&g_fb_vinfo;
    for (int i = 0; i < (int)sizeof(g_fb_vinfo); i++) p[i] = 0;
    if (ioctl(g_fb_fd, FBIOGET_VSCREENINFO, &g_fb_vinfo) < 0) {
        printf("[FB] ERROR: FBIOGET_VSCREENINFO failed\n"); exit(1);
    }
    printf("[FB] %dx%d @ %d bpp, stride=%d\n",
           g_fb_vinfo.xres, g_fb_vinfo.yres, g_fb_vinfo.bits_per_pixel,
           g_fb_vinfo.xres_virtual * g_fb_vinfo.bits_per_pixel / 8);
    g_fb_size = (long)g_fb_vinfo.xres_virtual * g_fb_vinfo.yres_virtual
              * (g_fb_vinfo.bits_per_pixel / 8);
    g_fb_map = mmap(0, (size_t)g_fb_size, PROT_READ | PROT_WRITE,
                    MAP_SHARED, g_fb_fd, 0);
    if (g_fb_map == MAP_FAILED) { printf("[FB] mmap failed\n"); exit(1); }
    for (long i = 0; i < g_fb_size; i++) g_fb_map[i] = 0;
}

static void fbdev_flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *pxmap)
{
    uint32_t w = (uint32_t)lv_area_get_width(area);
    uint32_t bpp = g_fb_vinfo.bits_per_pixel / 8;
    long stride = (long)g_fb_vinfo.xres * bpp;
    uint32_t *src = (uint32_t *)pxmap;
    for (uint32_t y = (uint32_t)area->y1; y <= (uint32_t)area->y2; y++) {
        uint32_t *dst = (uint32_t *)(g_fb_map + (long)y * stride
                                     + (long)area->x1 * bpp);
        for (uint32_t x = 0; x < w; x++) dst[x] = src[x];
        src += w;
    }
    lv_display_flush_ready(disp);
}

/* ----------------------- evdev touch ----------------------- */
static int g_touch_fd = -1;

/* 触摸屏原生分辨率 (实测 1024x600), 需缩放到屏幕 800x480 */
#define TOUCH_RAW_W  1024
#define TOUCH_RAW_H  600

static void evdev_init(void)
{
    /* 必须 O_NONBLOCK: 否则读完一批事件后 read() 会阻塞, 卡死整个 LVGL 循环 */
    g_touch_fd = open(TOUCH_DEV, O_RDONLY | O_NONBLOCK, 0);
    if (g_touch_fd < 0) { printf("[EV] WARNING: cannot open %s\n", TOUCH_DEV); return; }
    printf("[EV] Touch device opened: %s (raw %dx%d -> %dx%d)\n",
           TOUCH_DEV, TOUCH_RAW_W, TOUCH_RAW_H, SCREEN_W, SCREEN_H);
}

static void evdev_read_cb(lv_indev_t *indev, lv_indev_data_t *data)
{
    static int pressed = 0, raw_x = 0, raw_y = 0;
    LV_UNUSED(indev);
    if (g_touch_fd >= 0) {
        struct input_event ev;
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(g_touch_fd, &rfds);
        struct timeval tv = {0, 0};
        if (select(g_touch_fd + 1, &rfds, 0, 0, &tv) > 0) {
            /* 非阻塞模式: 读光当前所有事件, 无数据时 read 返回 -1 退出循环 */
            while (read(g_touch_fd, &ev, sizeof(ev)) == (long)sizeof(ev)) {
                switch (ev.type) {
                case EV_ABS:
                    if (ev.code == ABS_X || ev.code == ABS_MT_POSITION_X) raw_x = ev.value;
                    else if (ev.code == ABS_Y || ev.code == ABS_MT_POSITION_Y) raw_y = ev.value;
                    break;
                case EV_KEY:
                    if (ev.code == BTN_TOUCH) pressed = ev.value;
                    break;
                }
            }
        }
    }
    /* 1024x600 -> 800x480 缩放 */
    int x = raw_x * SCREEN_W / TOUCH_RAW_W;
    int y = raw_y * SCREEN_H / TOUCH_RAW_H;
    if (x < 0) x = 0; if (x >= SCREEN_W) x = SCREEN_W - 1;
    if (y < 0) y = 0; if (y >= SCREEN_H) y = SCREEN_H - 1;
    data->point.x = (lv_coord_t)x;
    data->point.y = (lv_coord_t)y;
    data->state = pressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
    data->continue_reading = false;
}

/* ----------------------- 智能体: 串口协议 ----------------------- */
#define AGENT_TIMEOUT_MS 20000
static lv_obj_t *g_msg_col;
static lv_obj_t *g_chat_ta;
static lv_obj_t *g_chat_status;
static int       g_msg_count = 0;
static uint32_t  g_ask_tick = 0;
static int       g_waiting = 0;

static void chat_add_msg(const char *text, int is_user)
{
    lv_obj_t *lbl = lv_label_create(g_msg_col);
    lv_label_set_text(lbl, text);
    lv_label_set_long_mode(lbl, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(lbl, lv_obj_get_content_width(g_msg_col));
    lv_obj_set_style_text_color(lbl,
        is_user ? lv_color_hex(0x7ee787) : lv_color_hex(0x88d8ff), 0);
    lv_obj_set_style_bg_color(lbl,
        is_user ? lv_color_hex(0x14351f) : lv_color_hex(0x10243a), 0);
    lv_obj_set_style_bg_opa(lbl, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(lbl, 6, 0);
    lv_obj_set_style_pad_hor(lbl, 8, 0);
    lv_obj_set_style_pad_ver(lbl, 4, 0);
    if (is_user) lv_obj_align(lbl, LV_ALIGN_TOP_RIGHT, 0, -1);
    else         lv_obj_align(lbl, LV_ALIGN_TOP_LEFT, 0, -1);

    if (++g_msg_count > 8) {
        lv_obj_t *old = lv_obj_get_child(g_msg_col, 0);
        if (old) { lv_obj_delete(old); g_msg_count--; }
    }
    lv_obj_scroll_to_view(lbl, LV_ANIM_ON);
}

static void agent_do_send(void)
{
    const char *txt = lv_textarea_get_text(g_chat_ta);
    if (!txt || !txt[0]) return;
    chat_add_msg(txt, 1);
    /* 协议帧 @@Q + 文本 + \n (一条物理行, 笔记本端按行读) */
    write(1, "@@Q", 3);
    write(1, txt, strlen(txt));
    write(1, "\n", 1);
    lv_textarea_set_text(g_chat_ta, "");
    lv_label_set_text(g_chat_status, "Thinking...");
    g_waiting = 1;
    g_ask_tick = lv_tick_get();
}

static void agent_send_cb(lv_event_t *e)
{
    LV_UNUSED(e);
    agent_do_send();
}

static void agent_kb_ready_cb(lv_event_t *e)
{
    /* 键盘右下角 OK/回车: 先发送内容, 再收起键盘 */
    agent_do_send();
    lv_obj_t *kb = lv_event_get_current_target(e);
    lv_obj_add_flag(kb, LV_OBJ_FLAG_HIDDEN);
    if (g_chat_ta) lv_obj_remove_state(g_chat_ta, LV_STATE_FOCUSED);
}

static void agent_kb_cancel_cb(lv_event_t *e)
{
    /* 键盘右上角收起键: 只收起, 不发送 */
    lv_obj_t *kb = lv_event_get_current_target(e);
    lv_obj_add_flag(kb, LV_OBJ_FLAG_HIDDEN);
    if (g_chat_ta) lv_obj_remove_state(g_chat_ta, LV_STATE_FOCUSED);
}

static void agent_kb_focus_cb(lv_event_t *e)
{
    lv_obj_t *kb = (lv_obj_t *)lv_event_get_user_data(e);
    lv_obj_remove_flag(kb, LV_OBJ_FLAG_HIDDEN);
    lv_keyboard_set_textarea(kb, g_chat_ta);
}

/* 主循环里轮询 stdin, 接收笔记本中转回来的回答 */
static char g_rx[1024];
static int  g_rx_len = 0;

static void agent_poll(void)
{
    fd_set rfds;
    FD_ZERO(&rfds);
    FD_SET(0, &rfds);
    struct timeval tv = {0, 0};
    if (select(1, &rfds, 0, 0, &tv) <= 0) {
        /* 超时兜底: 20s 没收到回答提示 */
        if (g_waiting && (int)(lv_tick_get() - g_ask_tick) > AGENT_TIMEOUT_MS) {
            g_waiting = 0;
            lv_label_set_text(g_chat_status, "No relay. Run agent_relay.py on PC.");
        }
        return;
    }
    char tmp[200];
    int n = read(0, tmp, sizeof(tmp) - 1);
    if (n <= 0) return;
    for (int i = 0; i < n; i++) {
        char ch = tmp[i];
        if (ch == '\n' || ch == '\r') {
            if (g_rx_len > 0) {
                g_rx[g_rx_len] = 0;
                if (g_rx_len >= 3 && g_rx[0] == '@' && g_rx[1] == '@'
                    && g_rx[2] == 'A') {
                    chat_add_msg(g_rx + 3, 0);
                    g_waiting = 0;
                    lv_label_set_text(g_chat_status, "Online");
                }
                g_rx_len = 0;
            }
        } else if (g_rx_len < (int)sizeof(g_rx) - 1) {
            g_rx[g_rx_len++] = ch;
        }
    }
}

/* ----------------------- 媒体浏览/播放 ----------------------- */
static uint8_t g_thumb_buf[MAX_PHOTOS][THUMB_H * THUMB_W * 3] __attribute__((aligned(8)));
static uint8_t g_view_buf[VIEW_H * VIEW_W * 3] __attribute__((aligned(8)));
static uint8_t g_vid_buf[VID_H * VID_W * 3] __attribute__((aligned(8)));

static char g_photo_path[MAX_PHOTOS][40];
static int  g_photo_count = 0;
static char g_video_path[MAX_VIDEOS][40];
static int  g_video_count = 0;

static int file_exists(const char *path)
{
    int fd = open(path, O_RDONLY, 0);
    if (fd >= 0) { close(fd); return 1; }
    return 0;
}

/* 拼 /tmp/media/<name> 到定长缓冲 */
static void media_path(char *dst, int cap, const char *name)
{
    const char *dir = MEDIA_DIR "/";
    int i = 0;
    while (dir[i] && i < cap - 1) { dst[i] = dir[i]; i++; }
    for (int k = 0; name[k] && i < cap - 1; k++) dst[i++] = name[k];
    dst[i] = 0;
}

/* ---- 照片全屏查看 (layer_top 覆盖层) ---- */
static lv_obj_t *g_view_overlay;
static int       g_view_fd = -1;
static uint8_t  *g_view_map = NULL;
static size_t    g_view_size = 0;

static void viewer_close_cb(lv_event_t *e)
{
    LV_UNUSED(e);
    if (g_view_map) { munmap(g_view_map, g_view_size); g_view_map = NULL; }
    if (g_view_fd >= 0) { close(g_view_fd); g_view_fd = -1; }
    if (g_view_overlay) { lv_obj_delete(g_view_overlay); g_view_overlay = NULL; }
}

static void photo_open_cb(lv_event_t *e)
{
    int idx = (int)(long)lv_event_get_user_data(e);
    if (idx < 0 || idx >= g_photo_count) return;

    int fd = media_map_file(g_photo_path[idx], &g_view_map, &g_view_size);
    if (fd < 0) { printf("[VIEW] open fail: %s\n", g_photo_path[idx]); return; }
    g_view_fd = fd;

    int w = 0, h = 0;
    for (int i = 0; i < VIEW_H * VIEW_W * 3; i++) g_view_buf[i] = 0;
    if (media_decode_jpeg(g_view_map, g_view_size, g_view_buf,
                          VIEW_W, VIEW_H, &w, &h) != 0) {
        viewer_close_cb(NULL);
        return;
    }
    printf("[VIEW] %s -> %dx%d\n", g_photo_path[idx], w, h);

    g_view_overlay = lv_obj_create(lv_layer_top());
    lv_obj_set_size(g_view_overlay, SCREEN_W, SCREEN_H);
    lv_obj_set_style_bg_color(g_view_overlay, lv_color_hex(0x05050f), 0);
    lv_obj_set_style_bg_opa(g_view_overlay, LV_OPA_COVER, 0);
    lv_obj_clear_flag(g_view_overlay, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *canvas = lv_canvas_create(g_view_overlay);
    lv_canvas_set_buffer(canvas, g_view_buf, w, h, LV_COLOR_FORMAT_RGB888);
    lv_obj_center(canvas);

    lv_obj_t *back = lv_btn_create(g_view_overlay);
    lv_obj_set_size(back, 90, 40);
    lv_obj_align(back, LV_ALIGN_TOP_LEFT, 10, 8);
    lv_obj_set_style_bg_color(back, lv_color_hex(0xff4757), 0);
    lv_obj_add_event_cb(back, viewer_close_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *bl = lv_label_create(back);
    lv_label_set_text(bl, LV_SYMBOL_LEFT " Back");
    lv_obj_center(bl);
    lv_obj_set_style_text_color(bl, lv_color_white(), 0);
}

/* ---- 视频播放 ---- */
typedef struct {
    lv_obj_t *overlay;
    lv_obj_t *canvas;
    lv_obj_t *status;
    lv_obj_t *play_btn;
    lv_timer_t *timer;
    int fd;
    uint8_t *map;
    size_t size;
    int frames;
    int idx;
    int playing;
} video_player_t;

static video_player_t g_vp;

static void player_close(void)
{
    if (g_vp.timer) { lv_timer_delete(g_vp.timer); g_vp.timer = NULL; }
    if (g_vp.map) { munmap(g_vp.map, g_vp.size); g_vp.map = NULL; }
    if (g_vp.fd >= 0) { close(g_vp.fd); g_vp.fd = -1; }
    if (g_vp.overlay) { lv_obj_delete(g_vp.overlay); g_vp.overlay = NULL; }
    g_vp.fd = -1; g_vp.map = NULL; g_vp.overlay = NULL;
}

static void player_back_cb(lv_event_t *e) { LV_UNUSED(e); player_close(); }

static void player_play_pause_cb(lv_event_t *e)
{
    LV_UNUSED(e);
    g_vp.playing = !g_vp.playing;
    lv_label_set_text(lv_obj_get_child(g_vp.play_btn, 0),
                      g_vp.playing ? LV_SYMBOL_PAUSE " Pause" : LV_SYMBOL_PLAY " Play");
}

static void player_tick_cb(lv_timer_t *t)
{
    LV_UNUSED(t);
    if (!g_vp.playing || !g_vp.map) return;
    size_t fs = 0, fe = 0;
    if (media_mjpeg_frame(g_vp.map, g_vp.size, g_vp.idx, &fs, &fe) != 0) {
        g_vp.idx = 0;  /* 循环播放 */
        if (media_mjpeg_frame(g_vp.map, g_vp.size, 0, &fs, &fe) != 0) return;
    }
    int w = 0, h = 0;
    if (media_decode_jpeg(g_vp.map + fs, fe - fs, g_vid_buf,
                          VID_W, VID_H, &w, &h) == 0) {
        lv_canvas_set_buffer(g_vp.canvas, g_vid_buf, w, h, LV_COLOR_FORMAT_RGB888);
        lv_obj_center(g_vp.canvas);
        g_vp.idx++;
    }
}

static void video_open_cb(lv_event_t *e)
{
    int idx = (int)(long)lv_event_get_user_data(e);
    if (idx < 0 || idx >= g_video_count) return;

    int fd = media_map_file(g_video_path[idx], &g_vp.map, &g_vp.size);
    if (fd < 0) { printf("[VID] open fail: %s\n", g_video_path[idx]); return; }
    g_vp.fd = fd;

    /* 数帧数 (扫 SOI/EOI) */
    g_vp.frames = 0;
    size_t s = 0, en = 0;
    while (media_mjpeg_frame(g_vp.map, g_vp.size, g_vp.frames, &s, &en) == 0)
        g_vp.frames++;
    printf("[VID] %s: %d frames, %u bytes\n", g_video_path[idx],
           g_vp.frames, (unsigned)g_vp.size);
    if (g_vp.frames == 0) { player_close(); return; }

    g_vp.idx = 0;
    g_vp.playing = 1;
    g_vp.overlay = lv_obj_create(lv_layer_top());
    lv_obj_set_size(g_vp.overlay, SCREEN_W, SCREEN_H);
    lv_obj_set_style_bg_color(g_vp.overlay, lv_color_hex(0x05050f), 0);
    lv_obj_set_style_bg_opa(g_vp.overlay, LV_OPA_COVER, 0);
    lv_obj_clear_flag(g_vp.overlay, LV_OBJ_FLAG_SCROLLABLE);

    g_vp.canvas = lv_canvas_create(g_vp.overlay);
    lv_obj_set_size(g_vp.canvas, VID_W, VID_H);
    lv_obj_align(g_vp.canvas, LV_ALIGN_CENTER, 0, -20);
    lv_obj_set_style_bg_color(g_vp.canvas, lv_color_black(), 0);

    g_vp.status = lv_label_create(g_vp.overlay);
    lv_label_set_text(g_vp.status, "Playing...");
    lv_obj_set_style_text_color(g_vp.status, lv_color_hex(0x2ed573), 0);
    lv_obj_align(g_vp.status, LV_ALIGN_BOTTOM_MID, 0, -58);

    g_vp.play_btn = lv_btn_create(g_vp.overlay);
    lv_obj_set_size(g_vp.play_btn, 130, 40);
    lv_obj_align(g_vp.play_btn, LV_ALIGN_BOTTOM_LEFT, 120, -10);
    lv_obj_set_style_bg_color(g_vp.play_btn, lv_color_hex(0x2ed573), 0);
    lv_obj_add_event_cb(g_vp.play_btn, player_play_pause_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *pl = lv_label_create(g_vp.play_btn);
    lv_label_set_text(pl, LV_SYMBOL_PAUSE " Pause");
    lv_obj_center(pl);
    lv_obj_set_style_text_color(pl, lv_color_black(), 0);

    lv_obj_t *back = lv_btn_create(g_vp.overlay);
    lv_obj_set_size(back, 110, 40);
    lv_obj_align(back, LV_ALIGN_BOTTOM_RIGHT, -120, -10);
    lv_obj_set_style_bg_color(back, lv_color_hex(0xff4757), 0);
    lv_obj_add_event_cb(back, player_back_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *bl = lv_label_create(back);
    lv_label_set_text(bl, LV_SYMBOL_LEFT " Back");
    lv_obj_center(bl);
    lv_obj_set_style_text_color(bl, lv_color_white(), 0);

    g_vp.timer = lv_timer_create(player_tick_cb, 120, NULL); /* ~8 fps */
}

/* ----------------------- 三个页面 ----------------------- */
static lv_obj_t *g_screen_chat;
static lv_obj_t *g_screen_photos;
static lv_obj_t *g_screen_video;

static void nav_goto(lv_event_t *e)
{
    int which = (int)(long)lv_event_get_user_data(e);
    lv_scr_load(which == 0 ? g_screen_chat :
                which == 1 ? g_screen_photos : g_screen_video);
}

static void create_nav_bar(lv_obj_t *parent, int active)
{
    lv_obj_t *bar = lv_obj_create(parent);
    lv_obj_set_size(bar, SCREEN_W, 56);
    lv_obj_align(bar, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(0x1a1a2e), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_pad_all(bar, 4, 0);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);

    const char *tabs[3] = {"CHAT", "PHOTOS", "VIDEO"};
    int btn_w = (SCREEN_W - 16) / 3;
    for (int i = 0; i < 3; i++) {
        lv_obj_t *btn = lv_btn_create(bar);
        lv_obj_set_size(btn, btn_w - 6, 48);
        lv_obj_align(btn, LV_ALIGN_LEFT_MID, i * btn_w + 8, 0);
        lv_obj_set_style_bg_color(btn,
            i == active ? lv_color_hex(0x00d9ff) : lv_color_hex(0x16213e), 0);
        lv_obj_set_style_bg_opa(btn, LV_OPA_COVER, 0);
        lv_obj_set_style_radius(btn, 8, 0);
        lv_obj_add_event_cb(btn, nav_goto, LV_EVENT_CLICKED, (void *)(long)i);
        lv_obj_t *label = lv_label_create(btn);
        lv_obj_center(label);
        lv_label_set_text(label, tabs[i]);
        lv_obj_set_style_text_color(label,
            i == active ? lv_color_black() : lv_color_white(), 0);
    }
}

/* ---------------- 自定义触摸键盘 (4 行, SEND 大键固定在第 3 行) ---------------- */
static const char *kb_map_lc[] = {
    "1#","q","w","e","r","t","y","u","i","o","p",LV_SYMBOL_BACKSPACE,"\n",
    "ABC","a","s","d","f","g","h","j","k","l",LV_SYMBOL_OK,"\n",
    "_","-","z","x","c","v","b","n","m",".",LV_SYMBOL_OK,"\n",
    LV_SYMBOL_LEFT," ",LV_SYMBOL_RIGHT,LV_SYMBOL_KEYBOARD,""
};
static const lv_buttonmatrix_ctrl_t kb_ctrl_lc[] = {
    1, 1,1,1,1,1,1,1,1,1,1, 2,
    2, 1,1,1,1,1,1,1,1,1, 2,
    1,1, 1,1,1,1,1,1,1,1, 3,
    2, 7, 2, 2
};
static const char *kb_map_uc[] = {
    "1#","Q","W","E","R","T","Y","U","I","O","P",LV_SYMBOL_BACKSPACE,"\n",
    "abc","A","S","D","F","G","H","J","K","L",LV_SYMBOL_OK,"\n",
    "_","-","Z","X","C","V","B","N","M",".",LV_SYMBOL_OK,"\n",
    LV_SYMBOL_LEFT," ",LV_SYMBOL_RIGHT,LV_SYMBOL_KEYBOARD,""
};
static const lv_buttonmatrix_ctrl_t kb_ctrl_uc[] = {
    1, 1,1,1,1,1,1,1,1,1,1, 2,
    2, 1,1,1,1,1,1,1,1,1, 2,
    1,1, 1,1,1,1,1,1,1,1, 3,
    2, 7, 2, 2
};
static const char *kb_map_sp[] = {
    "abc","1","2","3","4","5","6","7","8","9","0",LV_SYMBOL_BACKSPACE,"\n",
    "1#","(",")","-",":",";","/","!","?","'",LV_SYMBOL_OK,"\n",
    ",",".","+","*","=","\"","#","%","&","<",LV_SYMBOL_OK,"\n",
    LV_SYMBOL_LEFT," ",LV_SYMBOL_RIGHT,LV_SYMBOL_KEYBOARD,""
};
static const lv_buttonmatrix_ctrl_t kb_ctrl_sp[] = {
    2, 1,1,1,1,1,1,1,1,1,1, 2,
    2, 1,1,1,1,1,1,1,1,1, 2,
    1,1,1,1,1,1,1,1,1,1, 3,
    2, 7, 2, 2
};

static void create_screen_chat(void)
{
    g_screen_chat = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(g_screen_chat, lv_color_hex(0x0f0f23), 0);
    lv_obj_set_style_bg_opa(g_screen_chat, LV_OPA_COVER, 0);

    lv_obj_t *title = lv_label_create(g_screen_chat);
    lv_label_set_text(title, "Psych AI Assistant");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 8);

    g_msg_col = lv_obj_create(g_screen_chat);
    lv_obj_set_size(g_msg_col, SCREEN_W - 20, 286);
    lv_obj_align(g_msg_col, LV_ALIGN_TOP_MID, 0, 44);
    lv_obj_set_style_bg_color(g_msg_col, lv_color_hex(0x1a1a2e), 0);
    lv_obj_set_style_bg_opa(g_msg_col, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(g_msg_col, 8, 0);
    lv_obj_set_style_border_width(g_msg_col, 0, 0);
    lv_obj_set_style_pad_all(g_msg_col, 8, 0);
    lv_obj_set_flex_flow(g_msg_col, LV_FLEX_FLOW_COLUMN);

    g_chat_status = lv_label_create(g_screen_chat);
    lv_label_set_text(g_chat_status, "Offline - start agent_relay.py on PC");
    lv_obj_set_style_text_color(g_chat_status, lv_color_hex(0x888888), 0);
    lv_obj_set_style_text_font(g_chat_status, &lv_font_montserrat_14, 0);
    lv_obj_align(g_chat_status, LV_ALIGN_BOTTOM_LEFT, 14, -64);

    g_chat_ta = lv_textarea_create(g_screen_chat);
    lv_obj_set_size(g_chat_ta, SCREEN_W - 180, 44);
    lv_obj_align(g_chat_ta, LV_ALIGN_BOTTOM_MID, -80, -100);
    lv_textarea_set_one_line(g_chat_ta, true);
    lv_textarea_set_placeholder_text(g_chat_ta, "Ask me anything...");
    lv_obj_set_style_bg_color(g_chat_ta, lv_color_hex(0x1a1a2e), 0);
    lv_obj_set_style_text_color(g_chat_ta, lv_color_white(), 0);
    lv_obj_set_style_border_color(g_chat_ta, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_border_width(g_chat_ta, 2, 0);

    lv_obj_t *send_btn = lv_btn_create(g_screen_chat);
    lv_obj_set_size(send_btn, 140, 44);
    lv_obj_align(send_btn, LV_ALIGN_BOTTOM_MID, 90, -100);
    lv_obj_set_style_bg_color(send_btn, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_bg_opa(send_btn, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(send_btn, 8, 0);
    lv_obj_add_event_cb(send_btn, agent_send_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *lbl = lv_label_create(send_btn);
    lv_label_set_text(lbl, LV_SYMBOL_OK " SEND");
    lv_obj_center(lbl);
    lv_obj_set_style_text_color(lbl, lv_color_black(), 0);

    /* 屏幕键盘: 自定义 4 行布局, 底边抬高 56px 让开导航栏 */
    lv_obj_t *kb = lv_keyboard_create(g_screen_chat);
    lv_keyboard_set_map(kb, LV_KEYBOARD_MODE_TEXT_LOWER, kb_map_lc, kb_ctrl_lc);
    lv_keyboard_set_map(kb, LV_KEYBOARD_MODE_TEXT_UPPER, kb_map_uc, kb_ctrl_uc);
    lv_keyboard_set_map(kb, LV_KEYBOARD_MODE_SPECIAL, kb_map_sp, kb_ctrl_sp);
    lv_obj_set_size(kb, SCREEN_W, 190);
    lv_obj_align(kb, LV_ALIGN_BOTTOM_MID, 0, -56);
    lv_obj_set_style_pad_all(kb, 3, 0);
    lv_obj_set_style_pad_gap(kb, 3, 0);
    lv_obj_add_flag(kb, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_event_cb(kb, agent_kb_ready_cb, LV_EVENT_READY, NULL);
    lv_obj_add_event_cb(kb, agent_kb_cancel_cb, LV_EVENT_CANCEL, NULL);
    lv_obj_add_event_cb(g_chat_ta, agent_kb_focus_cb, LV_EVENT_FOCUSED, kb);

    create_nav_bar(g_screen_chat, 0);

    chat_add_msg("Hello! I am your Psych AI assistant.\nHow are you feeling today?", 0);
}

static void create_screen_photos(void)
{
    g_screen_photos = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(g_screen_photos, lv_color_hex(0x0f0f23), 0);
    lv_obj_set_style_bg_opa(g_screen_photos, LV_OPA_COVER, 0);

    lv_obj_t *title = lv_label_create(g_screen_photos);
    lv_label_set_text(title, LV_SYMBOL_IMAGE " Photos");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 16, 8);

    lv_obj_t *grid = lv_obj_create(g_screen_photos);
    lv_obj_set_size(grid, SCREEN_W - 16, SCREEN_H - 100);
    lv_obj_align(grid, LV_ALIGN_TOP_MID, 0, 44);
    lv_obj_set_style_bg_opa(grid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(grid, 0, 0);
    lv_obj_set_style_pad_all(grid, 4, 0);
    lv_obj_set_flex_flow(grid, LV_FLEX_FLOW_ROW_WRAP);

    /* 扫描固定文件名, 有就解码缩略图; 实际存在的文件紧凑放到 slot 0..count-1 */
    for (int i = 0; i < MAX_PHOTOS; i++) {
        char name[12];
        name[0] = 'p'; name[1] = (char)('1' + i);
        name[2] = '.'; name[3] = 'j'; name[4] = 'p'; name[5] = 'g'; name[6] = 0;
        char path[40];
        media_path(path, sizeof(path), name);
        if (!file_exists(path)) continue;

        int slot = g_photo_count;   /* 紧凑槽位号 */
        for (int k = 0; k < (int)sizeof(g_photo_path[slot]); k++)
            g_photo_path[slot][k] = 0;
        for (int k = 0; path[k] && k < (int)sizeof(g_photo_path[slot]) - 1; k++)
            g_photo_path[slot][k] = path[k];

        uint8_t *map = NULL; size_t sz = 0;
        int fd = media_map_file(path, &map, &sz);
        if (fd < 0) continue;
        int w = 0, h = 0;
        for (int k = 0; k < THUMB_H * THUMB_W * 3; k++) g_thumb_buf[slot][k] = 0;
        if (media_decode_jpeg(map, sz, g_thumb_buf[slot], THUMB_W, THUMB_H, &w, &h) != 0) {
            munmap(map, sz); close(fd);
            continue;
        }
        munmap(map, sz); close(fd);

        lv_obj_t *tile = lv_btn_create(grid);
        lv_obj_set_size(tile, THUMB_W + 12, THUMB_H + 34);
        lv_obj_set_style_bg_color(tile, lv_color_hex(0x16213e), 0);
        lv_obj_set_style_pad_all(tile, 4, 0);
        lv_obj_add_event_cb(tile, photo_open_cb, LV_EVENT_CLICKED,
                            (void *)(long)slot);

        lv_obj_t *cv = lv_canvas_create(tile);
        lv_canvas_set_buffer(cv, g_thumb_buf[slot], w, h, LV_COLOR_FORMAT_RGB888);
        lv_obj_align(cv, LV_ALIGN_TOP_MID, 0, 0);

        lv_obj_t *nm = lv_label_create(tile);
        lv_label_set_text(nm, name);
        lv_obj_set_style_text_color(nm, lv_color_white(), 0);
        lv_obj_align(nm, LV_ALIGN_BOTTOM_MID, 0, 0);

        g_photo_count++;
        printf("[PHOTO] %s loaded (%dx%d)\n", path, w, h);
        if (g_photo_count >= MAX_PHOTOS) break;
    }

    if (g_photo_count == 0) {
        lv_obj_t *empty = lv_label_create(g_screen_photos);
        lv_label_set_text(empty,
            "No photos.\nUpload JPGs to " MEDIA_DIR " (p1.jpg ... p8.jpg)\nvia serial base64.");
        lv_obj_set_style_text_color(empty, lv_color_hex(0x888888), 0);
        lv_obj_align(empty, LV_ALIGN_CENTER, 0, -20);
        lv_label_set_long_mode(empty, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(empty, 600);
    }

    create_nav_bar(g_screen_photos, 1);
}

static void create_screen_video(void)
{
    g_screen_video = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(g_screen_video, lv_color_hex(0x0f0f23), 0);
    lv_obj_set_style_bg_opa(g_screen_video, LV_OPA_COVER, 0);

    lv_obj_t *title = lv_label_create(g_screen_video);
    lv_label_set_text(title, LV_SYMBOL_VIDEO " Videos");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00d9ff), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 16, 8);

    for (int i = 0; i < MAX_VIDEOS; i++) {
        char name[12];
        name[0] = 'v'; name[1] = (char)('1' + i);
        name[2] = '.'; name[3] = 'm'; name[4] = 'j'; name[5] = 'p';
        name[6] = 'e'; name[7] = 'g'; name[8] = 0;
        char path[40];
        media_path(path, sizeof(path), name);
        if (!file_exists(path)) continue;

        int slot = g_video_count;
        for (int k = 0; k < (int)sizeof(g_video_path[slot]); k++)
            g_video_path[slot][k] = 0;
        for (int k = 0; path[k] && k < (int)sizeof(g_video_path[slot]) - 1; k++)
            g_video_path[slot][k] = path[k];

        lv_obj_t *row = lv_btn_create(g_screen_video);
        lv_obj_set_size(row, SCREEN_W - 60, 70);
        lv_obj_align(row, LV_ALIGN_TOP_MID, 0, 56 + slot * 84);
        lv_obj_set_style_bg_color(row, lv_color_hex(0x16213e), 0);
        lv_obj_add_event_cb(row, video_open_cb, LV_EVENT_CLICKED,
                            (void *)(long)slot);

        lv_obj_t *nm = lv_label_create(row);
        lv_label_set_text(nm, name);
        lv_obj_set_style_text_color(nm, lv_color_white(), 0);
        lv_obj_set_style_text_font(nm, &lv_font_montserrat_16, 0);
        lv_obj_align(nm, LV_ALIGN_LEFT_MID, 20, 0);

        lv_obj_t *play = lv_label_create(row);
        lv_label_set_text(play, LV_SYMBOL_PLAY " TAP TO PLAY");
        lv_obj_set_style_text_color(play, lv_color_hex(0x2ed573), 0);
        lv_obj_align(play, LV_ALIGN_RIGHT_MID, -20, 0);

        g_video_count++;
        printf("[VIDEO] %s found\n", path);
        if (g_video_count >= MAX_VIDEOS) break;
    }

    if (g_video_count == 0) {
        lv_obj_t *empty = lv_label_create(g_screen_video);
        lv_label_set_text(empty,
            "No videos.\nUpload MJPEG to " MEDIA_DIR " (v1.mjpeg ... v2.mjpeg)\nvia serial base64.");
        lv_obj_set_style_text_color(empty, lv_color_hex(0x888888), 0);
        lv_obj_align(empty, LV_ALIGN_CENTER, 0, -20);
        lv_label_set_long_mode(empty, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(empty, 600);
    }

    create_nav_bar(g_screen_video, 2);
}

/* ----------------------- tick ----------------------- */
static uint32_t tick_cb(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0) return 0;
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

int main(int argc, char *argv[])
{
    (void)argc; (void)argv;
    /* 忽略串口挂断信号: 这样 SecureCRT 断开、交给 agent_relay.py 接管时程序不被杀 */
    signal(1 /*SIGHUP*/, (sighandler_t)1 /*SIG_IGN*/);

    printf("\n========================================\n");
    printf("  LVGL GEC6818 -- Psych AI Terminal\n");
    printf("  %dx%d | fb:%s touch:%s media:%s\n",
           SCREEN_W, SCREEN_H, FB_DEV, TOUCH_DEV, MEDIA_DIR);
    printf("========================================\n\n");

    /* 媒体目录 (已存在也没关系) */
    mkdir("/tmp", 0755);
    mkdir(MEDIA_DIR, 0755);

    fbdev_init();
    lv_init();

    g_display = lv_display_create(SCREEN_W, SCREEN_H);
    lv_display_set_color_format(g_display, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_flush_cb(g_display, fbdev_flush_cb);
    uint32_t buf_stride = lv_draw_buf_width_to_stride(SCREEN_W, LV_COLOR_FORMAT_XRGB8888);
    uint32_t buf_bytes  = buf_stride * SCREEN_H;
    void *buf1 = malloc(buf_bytes);
    if (!buf1) { printf("[MAIN] draw buffer alloc failed\n"); exit(1); }
    lv_display_set_buffers(g_display, buf1, NULL, buf_bytes,
                           LV_DISPLAY_RENDER_MODE_FULL);

    evdev_init();
    lv_indev_t *indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, evdev_read_cb);
    lv_tick_set_cb(tick_cb);

    create_screen_chat();
    create_screen_photos();
    create_screen_video();
    lv_scr_load(g_screen_chat);

    printf("Ready. Photos=%d Videos=%d\n", g_photo_count, g_video_count);
    printf("Agent protocol: board->PC @@Q..., PC->board @@A...\n");
    printf("[BUILD] custom keyboard v3\n\n");

    while (1) {
        agent_poll();
        lv_timer_handler();
        usleep(5000);
    }
    return 0;
}
