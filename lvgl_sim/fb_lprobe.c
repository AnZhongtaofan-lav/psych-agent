/* fb_lprobe.c -- 画 fb 坐标边界标记, 确定 framebuffer 与物理面板的方向映射.
 * 红=fb顶行(y=0)  蓝=fb底行(y=479)  绿=fb左列(x=0)  白=fb右列(x=799)  黄=中心 */
#include "linux_shim.h"

int main(void)
{
    int fd = open("/dev/fb0", O_RDWR, 0);
    if (fd < 0) { printf("open fail\n"); return 1; }

    struct fb_var_screeninfo vi;
    char *z = (char *)&vi;
    for (unsigned i = 0; i < sizeof(vi); i++) z[i] = 0;
    ioctl(fd, FBIOGET_VSCREENINFO, &vi);
    int W = vi.xres, H = vi.yres, bpp = vi.bits_per_pixel / 8;
    long stride = (long)vi.xres * bpp;
    long size = stride * vi.yres_virtual;
    printf("fb %dx%d bpp=%d stride=%d\n", W, H, vi.bits_per_pixel, (int)stride);

    uint8_t *m = (uint8_t *)mmap(0, size, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
    if (m == MAP_FAILED) { printf("mmap fail\n"); return 1; }
    for (long i = 0; i < size; i++) m[i] = 0;  /* 全黑底 */

    /* 颜色是 B,G,R,X */
    /* 红: fb 顶行 y=0..3 (粗) */
    for (int y = 0; y < 4; y++)
        for (int x = 0; x < W; x++) {
            uint8_t *p = m + (long)y*stride + x*bpp;
            p[0]=0; p[1]=0; p[2]=255;
        }
    /* 蓝: fb 底行 y=H-4..H-1 */
    for (int y = H-4; y < H; y++)
        for (int x = 0; x < W; x++) {
            uint8_t *p = m + (long)y*stride + x*bpp;
            p[0]=255; p[1]=0; p[2]=0;
        }
    /* 绿: fb 左列 x=0..3 */
    for (int y = 0; y < H; y++)
        for (int x = 0; x < 4; x++) {
            uint8_t *p = m + (long)y*stride + x*bpp;
            p[0]=0; p[1]=255; p[2]=0;
        }
    /* 白: fb 右列 x=W-4..W-1 */
    for (int y = 0; y < H; y++)
        for (int x = W-4; x < W; x++) {
            uint8_t *p = m + (long)y*stride + x*bpp;
            p[0]=255; p[1]=255; p[2]=255;
        }
    /* 黄: 中心 40x40 方块, 中心在 (W/2,H/2) */
    for (int y = H/2-20; y < H/2+20; y++)
        for (int x = W/2-20; x < W/2+20; x++) {
            uint8_t *p = m + (long)y*stride + x*bpp;
            p[0]=0; p[1]=255; p[2]=255;
        }

    printf("DONE: red=fb-top blue=fb-bottom green=fb-left white=fb-right yellow=center\n");
    while (1) usleep(200000);
    return 0;
}
