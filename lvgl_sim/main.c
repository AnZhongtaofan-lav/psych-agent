#include "lvgl/lvgl.h"
#include "lvgl/demos/lv_demos.h"
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include "./ui/ui.h"
// 初始化Linux显示设备 
static void lv_linux_disp_init(void)
{
    // 创建帧缓冲显示设备
    lv_display_t *disp = lv_linux_fbdev_create();
    // 设置帧缓冲显示设备的文件路径为/dev/fb0
    lv_linux_fbdev_set_file(disp, "/dev/fb0");
}
// 外部声明字典数组
extern const lv_pinyin_dict_t my_lv_ime_pinyin_dict[];

//初始化拼音输入法 
static void lv_pinyin_init(lv_obj_t *keyboard,lv_obj_t *textarea)
{
    // 创建拼音输入法
    lv_obj_t *pinyin = lv_ime_pinyin_create(lv_screen_active());
    // 把输入法设置到键盘中
    lv_ime_pinyin_set_keyboard(pinyin, keyboard);
    //设置字典
    lv_ime_pinyin_set_dict(pinyin, my_lv_ime_pinyin_dict);

    //创建一个中文字体 ， simkai.ttf 中文字模文件
    lv_font_t * simkai_font = lv_freetype_font_create("./simkai.ttf",  //👈字模文件
                                                      LV_FREETYPE_FONT_RENDER_MODE_BITMAP,
                                                      28,   //👈字体大小
                                                      LV_FREETYPE_FONT_STYLE_NORMAL);

    if(!simkai_font) {
        printf("FreeType font create failed!\n");
        return;
    }
    //设置拼音输入法的中文字体
    lv_obj_set_style_text_font(pinyin, simkai_font, 0);

    //设置输入框的中文字体
    lv_obj_set_style_text_font(textarea, simkai_font, 0);
}

//初始化中文对象 
void lv_obj_chinese_init(lv_obj_t *obj,int size)
{
    //创建一个中文字体 ， simkai.ttf 中文字模文件
    lv_font_t * simkai_font = lv_freetype_font_create("./simkai.ttf",  //👈字模文件
                                                      LV_FREETYPE_FONT_RENDER_MODE_BITMAP,
                                                      size,   //👈字体大小
                                                      LV_FREETYPE_FONT_STYLE_NORMAL);
       //设置对象的中文字体
    lv_obj_set_style_text_font(obj, simkai_font, 0);
}

int main(void)
{
    // 初始化LVGL库，设置内部状态、内存管理和任务系统
    lv_init();
    /*Linux display device init*/
    // 调用Linux显示设备初始化函数，根据配置创建帧缓冲或SDL窗口显示
    lv_linux_disp_init();

    // 创建输入设备
    lv_indev_t *touch = lv_evdev_create(LV_INDEV_TYPE_POINTER, "/dev/input/event0");
    // 校准输入设备屏幕坐标
    lv_evdev_set_calibration(touch, 0, 0, 1024, 600); // 黑色边框的屏幕 ⭐
    // lv_evdev_set_calibration(touch, 0, 0, 800, 480);  // 蓝色边框的屏幕 ⭐

    ui_init();  //初始化ui界面

    // 初始化拼音输入法
    lv_pinyin_init(ui_Keyboard1,ui_TextArea1);

    //把标签初始化为中文 
    lv_obj_chinese_init(ui_Label1,28);

    /*Handle LVGL tasks*/
    // 主循环：持续处理LVGL定时器任务，驱动UI更新和动画
    while (1)
    {
        lv_timer_handler(); // 执行LVGL定时器处理，更新屏幕显示和处理事件
        usleep(5000);       // 休眠5毫秒，避免CPU占用过高，同时保证UI流畅性
    }
    return 0;
}
