/* fb_probe.c -- 最小 framebuffer 探测程序, 用来定位 gec6818_app 段错误位置.
 * 每一步都打印标号, 崩在哪一步一目了然.
 * 编译: 和 syscalls.c 一起链接, 不依赖 LVGL. */

#include "linux_shim.h"

int main(void)
{
    printf("[1] start fb_probe\n");

    /* --- step 1: open --- */
    int fd = open("/dev/fb0", O_RDWR, 0);
    printf("[2] open returned fd=%d\n", fd);
    if (fd < 0) {
        printf("[!] open failed, stop\n");
        exit(1);
    }

    /* --- step 2: ioctl FBIOGET_VSCREENINFO --- */
    struct fb_var_screeninfo vinfo;
    char *p = (char *)&vinfo;
    for (unsigned i = 0; i < sizeof(vinfo); i++) p[i] = 0;
    printf("[3] before ioctl, sizeof(vinfo)=%d, &vinfo=0x%x\n",
           (int)sizeof(vinfo), (unsigned)(long)&vinfo);
    int r = ioctl(fd, FBIOGET_VSCREENINFO, &vinfo);
    printf("[4] ioctl returned r=%d\n", r);
    printf("[5] xres=%d yres=%d xv=%d yv=%d bpp=%d\n",
           vinfo.xres, vinfo.yres, vinfo.xres_virtual,
           vinfo.yres_virtual, vinfo.bits_per_pixel);

    /* --- step 3: mmap --- */
    long size = (long)vinfo.xres_virtual * vinfo.yres_virtual
              * (vinfo.bits_per_pixel / 8);
    printf("[6] before mmap size=%d\n", (int)size);
    uint8_t *map = (uint8_t *)mmap(0, (size_t)size,
                                   PROT_READ | PROT_WRITE,
                                   MAP_SHARED, fd, 0);
    printf("[7] mmap returned map=0x%x\n", (unsigned)(long)map);
    if (map == MAP_FAILED || map == 0) {
        printf("[!] mmap failed\n");
        exit(1);
    }

    /* --- step 4: 左上角画 100x100 红色块 (BGRX: 蓝0 绿0 红FF) --- */
    int bpp = vinfo.bits_per_pixel / 8;
    for (int y = 0; y < 100; y++) {
        for (int x = 0; x < 100; x++) {
            uint8_t *px = map + (long)(y * vinfo.xres + x) * bpp;
            px[0] = 0x00;   /* B */
            px[1] = 0x00;   /* G */
            px[2] = 0xFF;   /* R */
            px[3] = 0x00;   /* X */
        }
    }
    printf("[8] red 100x100 block drawn at top-left\n");

    /* --- step 5: 再画个绿色块 --- */
    for (int y = 0; y < 100; y++) {
        for (int x = 100; x < 200; x++) {
            uint8_t *px = map + (long)(y * vinfo.xres + x) * bpp;
            px[0] = 0x00;
            px[1] = 0xFF;
            px[2] = 0x00;
            px[3] = 0x00;
        }
    }
    printf("[9] green block drawn. DONE - screen should show 2 blocks\n");

    while (1) {
        usleep(100000);
    }
    return 0;
}
