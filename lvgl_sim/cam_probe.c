/* cam_probe.c -- 探测 /dev/video0: 能力/格式/分辨率, 并尝试抓 1 帧看大小 */
#include "linux_shim.h"

static void fourcc(uint32_t f, char *out) {
    out[0] = f & 0xff; out[1] = (f>>8)&0xff; out[2] = (f>>16)&0xff;
    out[3] = (f>>24)&0xff; out[4] = 0;
}

/* 编译期结构大小校验 (和内核 ioctl _IOC size 必须一致) */
typedef char _chk_cap[(int)sizeof(struct v4l2_capability)==104 ? 1 : -1];
typedef char _chk_fmt[(int)sizeof(struct v4l2_fmtdesc)==64 ? 1 : -1];
typedef char _chk_frmsz[(int)sizeof(struct v4l2_frmsizeenum)==44 ? 1 : -1];
typedef char _chk_req[(int)sizeof(struct v4l2_requestbuffers)==20 ? 1 : -1];
typedef char _chk_buf[(int)sizeof(struct v4l2_buffer)==88 ? 1 : -1];
typedef char _chk_vfmt[(int)sizeof(struct v4l2_format)==204 ? 1 : -1];

int main(void)
{
    int fd = open("/dev/video0", O_RDWR, 0);
    if (fd < 0) { printf("[!] open /dev/video0 fail\n"); return 1; }
    printf("[1] opened fd=%d\n", fd);

    /* QUERYCAP */
    struct v4l2_capability cap;
    char *z = (char*)&cap; for (unsigned i=0;i<sizeof(cap);i++) z[i]=0;
    if (ioctl(fd, VIDIOC_QUERYCAP, &cap) < 0) { printf("[!] QUERYCAP fail\n"); return 1; }
    printf("[2] driver='%s' card='%s' bus='%s' ver=%d caps=0x%x devcaps=0x%x\n",
           cap.driver, cap.card, cap.bus_info, cap.version,
           cap.capabilities, cap.device_caps);
    printf("    VIDEO_CAPTURE=%d STREAMING=%d\n",
           (cap.device_caps & V4L2_CAP_VIDEO_CAPTURE)?1:0,
           (cap.device_caps & V4L2_CAP_STREAMING)?1:0);

    /* ENUM_FMT */
    printf("[3] formats:\n");
    uint32_t fmts[16]; int nfmt = 0;
    for (int i = 0; i < 16; i++) {
        struct v4l2_fmtdesc fd2;
        z=(char*)&fd2; for (unsigned k=0;k<sizeof(fd2);k++) z[k]=0;
        fd2.index = i; fd2.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (ioctl(fd, VIDIOC_ENUM_FMT, &fd2) < 0) break;
        char cc[5]; fourcc(fd2.pixelformat, cc);
        printf("    [%d] %s  '%s'\n", i, cc, fd2.description);
        fmts[nfmt++] = fd2.pixelformat;
    }
    if (nfmt == 0) printf("    (none)\n");

    /* 对每个格式 ENUM_FRAMESIZES */
    for (int f = 0; f < nfmt; f++) {
        char cc[5]; fourcc(fmts[f], cc);
        for (int i = 0; i < 20; i++) {
            struct v4l2_frmsizeenum fs;
            z=(char*)&fs; for (unsigned k=0;k<sizeof(fs);k++) z[k]=0;
            fs.index = i; fs.pixel_format = fmts[f];
            if (ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &fs) < 0) break;
            if (fs.type == 1)
                printf("[4] %s size[%d]=%dx%d\n", cc, i, fs.discrete.width, fs.discrete.height);
            else {
                printf("[4] %s range %d-%d x %d-%d (step %d,%d)\n", cc,
                       fs.stepwise.min_width, fs.stepwise.max_width,
                       fs.stepwise.min_height, fs.stepwise.max_height,
                       fs.stepwise.step_width, fs.stepwise.step_height);
                break;
            }
        }
    }

    /* 尝试设置 MJPEG 640x480, 看 G_FMT 回来什么 */
    uint32_t try_fmts[] = { V4L2_PIX_FMT_MJPEG, V4L2_PIX_FMT_YUYV, V4L2_PIX_FMT_RGB565 };
    int try_w[] = { 640, 320, 1280 };
    int try_h[] = { 480, 240, 720 };
    for (int k = 0; k < 3; k++) {
        struct v4l2_format fmt;
        z=(char*)&fmt; for (unsigned i=0;i<sizeof(fmt);i++) z[i]=0;
        fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        fmt.fmt.pix.width = try_w[k]; fmt.fmt.pix.height = try_h[k];
        fmt.fmt.pix.pixelformat = try_fmts[k]; fmt.fmt.pix.field = V4L2_FIELD_NONE;
        int r = ioctl(fd, VIDIOC_S_FMT, &fmt);
        char cc[5]; fourcc(fmt.fmt.pix.pixelformat, cc);
        printf("[5] S_FMT %s %dx%d r=%d -> %dx%d got=%s bpl=%d sizeimg=%d\n",
               (k==0?"MJPG":k==1?"YUYV":"RGB565"), try_w[k], try_h[k], r,
               fmt.fmt.pix.width, fmt.fmt.pix.height, cc,
               fmt.fmt.pix.bytesperline, fmt.fmt.pix.sizeimage);
    }

    close(fd);
    printf("[6] probe done\n");
    return 0;
}
