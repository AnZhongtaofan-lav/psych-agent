/* cam_scan.c -- 遍历 /dev/video0..9, 找出真正支持采集的摄像头节点 */
#include "linux_shim.h"

static void fourcc(uint32_t f, char *out) {
    out[0] = f & 0xff; out[1] = (f>>8)&0xff; out[2] = (f>>16)&0xff;
    out[3] = (f>>24)&0xff; out[4] = 0;
}

int main(void)
{
    for (int n = 0; n <= 9; n++) {
        char path[24];
        const char *p = "/dev/video";
        int i = 0;
        while (p[i]) { path[i] = p[i]; i++; }
        path[i++] = (char)('0' + n); path[i] = 0;

        int fd = open(path, O_RDWR, 0);
        if (fd < 0) {   /* 只读再试一次 (有些节点权限) */
            fd = open(path, O_RDONLY, 0);
            if (fd < 0) continue;  /* 节点不存在或打不开, 跳过 */
        }

        struct v4l2_capability cap;
        char *z = (char*)&cap; for (unsigned k=0;k<sizeof(cap);k++) z[k]=0;
        if (ioctl(fd, VIDIOC_QUERYCAP, &cap) < 0) {
            printf("%s: open ok but QUERYCAP fail\n", path);
            close(fd); continue;
        }
        /* 优先看 device_caps (有 DEVICE_CAPS 位时), 否则看 capabilities */
        uint32_t dc = (cap.capabilities & 0x80000000) ? cap.device_caps : cap.capabilities;
        int cap_cap  = (dc & 0x00000001) ? 1 : 0;
        int cap_str  = (dc & 0x04000000) ? 1 : 0;
        int cap_mpln = (dc & 0x00001000) ? 1 : 0;
        printf("%s: '%s' drv='%s' devcaps=0x%x CAPTURE=%d STREAM=%d MPLANE=%d\n",
               path, cap.card, cap.driver, dc, cap_cap, cap_str, cap_mpln);

        /* 如果是采集设备, 列格式和分辨率 */
        if (cap_cap && cap_str) {
            for (int fi = 0; fi < 12; fi++) {
                struct v4l2_fmtdesc fd2;
                z=(char*)&fd2; for (unsigned k=0;k<sizeof(fd2);k++) z[k]=0;
                fd2.index = fi; fd2.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
                if (ioctl(fd, VIDIOC_ENUM_FMT, &fd2) < 0) break;
                char cc[5]; fourcc(fd2.pixelformat, cc);
                printf("    fmt[%d] %s '%s'\n", fi, cc, fd2.description);
                for (int si = 0; si < 12; si++) {
                    struct v4l2_frmsizeenum fs;
                    z=(char*)&fs; for (unsigned k=0;k<sizeof(fs);k++) z[k]=0;
                    fs.index = si; fs.pixel_format = fd2.pixelformat;
                    if (ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &fs) < 0) break;
                    if (fs.type == 1)
                        printf("        %dx%d\n", fs.discrete.width, fs.discrete.height);
                    else { printf("        range %d-%dx%d-%d\n",
                        fs.stepwise.min_width,fs.stepwise.max_width,
                        fs.stepwise.min_height,fs.stepwise.max_height); break; }
                }
            }
        }
        close(fd);
    }
    printf("=== scan done ===\n");
    return 0;
}
