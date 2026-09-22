#include <stdio.h>
#include "lvgl/lvgl.h"
int main(void) {
    printf("sizeof(lv_color_t)=%u\n", (unsigned)sizeof(lv_color_t));
    printf("stride(800,XRGB8888)=%u\n", lv_draw_buf_width_to_stride(800, LV_COLOR_FORMAT_XRGB8888));
    printf("bpp=%u\n", lv_color_format_get_bpp(LV_COLOR_FORMAT_XRGB8888));
    printf("need=%u\n", lv_draw_buf_width_to_stride(800, LV_COLOR_FORMAT_XRGB8888) * 480);
    return 0;
}
