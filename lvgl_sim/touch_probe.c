/* touch_probe.c -- 抓 /dev/input/event0 原始触摸事件
 * 用法: 运行后依次点屏幕 左上->右上->右下->左下->中心, 每个位置按住1秒
 * 打印 type/code/value, 并持续更新 X/Y 的最小/最大值和按压事件统计 */
#include "linux_shim.h"

struct input_event_pb {
    long tv_sec;
    long tv_usec;
    unsigned short type;
    unsigned short code;
    int value;
};

/* Linux input 事件类型/code */
#define EV_SYN_PB      0
#define EV_KEY_PB      1
#define EV_ABS_PB      3
#define ABS_X_PB       0x00
#define ABS_Y_PB       0x01
#define ABS_PRESSURE_PB 0x18
#define ABS_MT_SLOT_PB  0x2f
#define ABS_MT_POS_X_PB 0x35
#define ABS_MT_POS_Y_PB 0x36
#define ABS_MT_TRK_PB   0x39
#define BTN_TOUCH_PB    0x14a
#define BTN_TOOL_FINGER_PB 0x145

int main(void)
{
    int fd = open("/dev/input/event0", O_RDONLY, 0);
    if (fd < 0) { printf("open event0 failed\n"); return 1; }
    printf("touch probe ready. Tap 4 corners + center...\n");
    printf("(type code value raw)\n");

    int minx = 99999, maxx = -1, miny = 99999, maxy = -1;
    int press_events = 0;
    int last_x = -1, last_y = -1;
    int n = 0;

    while (n < 400) {
        struct input_event_pb ev;
        int r = read(fd, &ev, sizeof(ev));
        if (r != (int)sizeof(ev)) continue;
        n++;

        const char *tn = "?";
        if (ev.type == EV_SYN_PB) tn = "SYN";
        else if (ev.type == EV_KEY_PB) tn = "KEY";
        else if (ev.type == EV_ABS_PB) tn = "ABS";

        if (ev.type == EV_ABS_PB) {
            if (ev.code == ABS_X_PB || ev.code == ABS_MT_POS_X_PB) {
                last_x = ev.value;
                if (ev.value < minx) minx = ev.value;
                if (ev.value > maxx) maxx = ev.value;
            } else if (ev.code == ABS_Y_PB || ev.code == ABS_MT_POS_Y_PB) {
                last_y = ev.value;
                if (ev.value < miny) miny = ev.value;
                if (ev.value > maxy) maxy = ev.value;
            } else if (ev.code == ABS_PRESSURE_PB) {
                if (ev.value > 0) press_events++;
            }
            printf("[%3d] %s code=0x%03x val=%d  (X %d..%d Y %d..%d press=%d)\n",
                   n, tn, ev.code, ev.value, minx, maxx, miny, maxy, press_events);
        } else if (ev.type == EV_KEY_PB) {
            printf("[%3d] KEY code=0x%03x val=%d  << %s\n", n, ev.code, ev.value,
                   (ev.code == BTN_TOUCH_PB) ? "BTN_TOUCH" :
                   (ev.code == BTN_TOOL_FINGER_PB) ? "BTN_TOOL_FINGER" : "other key");
        }
        /* SYN 时若有有效坐标打印一行汇总 */
        if (ev.type == EV_SYN_PB && (last_x >= 0 || last_y >= 0)) {
            printf("      >>> pos=(%d,%d)\n", last_x, last_y);
        }
    }
    printf("\n==== SUMMARY ====\n");
    printf("X range: %d .. %d\n", minx, maxx);
    printf("Y range: %d .. %d\n", miny, maxy);
    printf("ABS_PRESSURE(>0) events: %d\n", press_events);
    close(fd);
    return 0;
}
