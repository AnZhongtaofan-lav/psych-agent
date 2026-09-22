/* ============================================================
 * linux_shim.h — 在 arm-none-eabi-gcc 环境下, 代替 <linux/fb.h>
 * <linux/videodev2.h> <linux/input.h> <sys/mman.h> <sys/ioctl.h>
 * <sys/select.h> <time.h> <errno.h> 以及 syscalls.c 里实现的 C runtime.
 *
 * 不 typedef 基本类型 (用编译器自带的 stdint.h / stddef.h)
 * 不 #include 任何 newlib 系统头 (避免 libc 依赖)
 * 只声明 main_board.c 真正用到的结构和符号。
 * ============================================================ */
#ifndef LINUX_SHIM_H
#define LINUX_SHIM_H

/* ----------------------- 编译器自带基本类型 ----------------------- */
#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>

/* 编译器 stdint/stddef 没有 ssize_t/off_t, 自己定义 */
typedef long        ssize_t;
typedef long        off_t;

/* ----------------------- O_* / FD / fd_set ----------------------- */
#define O_RDONLY       0
#define O_WRONLY       1
#define O_RDWR         2
#define O_NONBLOCK   04000
#define O_CREAT      0100

/* select 用 fd_set — Linux 上是 1024 bit 位图 */
typedef struct { unsigned long fds[1024 / (8 * sizeof(unsigned long))]; } fd_set;
#define FD_SETSIZE 1024
#define FD_ZERO(set) do { unsigned int _i; for (_i=0; _i<sizeof((set)->fds)/sizeof((set)->fds[0]); _i++) (set)->fds[_i]=0; } while(0)
#define FD_SET(fd, set) do { \
    unsigned int _b = (unsigned int)(fd); \
    (set)->fds[_b / (8*sizeof(unsigned long))] |= (1UL << (_b % (8*sizeof(unsigned long)))); \
} while(0)
#define FD_CLR(fd, set) do { \
    unsigned int _b = (unsigned int)(fd); \
    (set)->fds[_b / (8*sizeof(unsigned long))] &= ~(1UL << (_b % (8*sizeof(unsigned long)))); \
} while(0)
#define FD_ISSET(fd, set) ( ((set)->fds[(fd)/(8*sizeof(unsigned long))] >> ((fd) % (8*sizeof(unsigned long)))) & 1 )

/* timeval / timespec */
struct timeval {
    long tv_sec;
    long tv_usec;
};
struct timespec {
    long tv_sec;
    long tv_nsec;
};
#define CLOCK_REALTIME       0
#define CLOCK_MONOTONIC     1

/* PROT/MAP */
#define PROT_READ    0x1
#define PROT_WRITE   0x2
#define PROT_EXEC    0x4
#define MAP_SHARED    0x01
#define MAP_PRIVATE   0x02
#define MAP_FAILED   ((void*)-1)

/* ----------------------- syscalls.c 里实现的函数原型 ----------------------- */
/* 文件 I/O */
int     open(const char *p, int f, int m);
int     close(int fd);
ssize_t read(int fd, void *b, size_t n);
ssize_t write(int fd, const void *b, size_t n);
off_t   lseek(int fd, off_t o, int w);
int     ioctl(int fd, unsigned long req, void *arg);
int     select(int n, void *r, void *w, void *e, void *t);

/* 内存 */
void   *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off);
int     munmap(void *addr, size_t len);
int     mkdir(const char *path, uint32_t mode);
typedef void (*sighandler_t)(int);
sighandler_t signal(int sig, sighandler_t h);
void   *malloc(size_t n);
void    free(void *p);
void   *calloc(size_t n, size_t s);
void   *realloc(void *p, size_t n);

/* 字符串 */
void   *memset(void *s, int c, size_t n);
void   *memcpy(void *d, const void *s, size_t n);
void   *memmove(void *d, const void *s, size_t n);
int     memcmp(const void *a, const void *b, size_t n);
size_t  strlen(const char *s);
char   *strcpy(char *d, const char *s);
char   *strncpy(char *d, const char *s, size_t n);
int     strcmp(const char *a, const char *b);
int     strncmp(const char *a, const char *b, size_t n);
char   *strchr(const char *s, int c);
char   *strrchr(const char *s, int c);
char   *strerror(int err);

/* 格式化 */
int     printf(const char *fmt, ...);
int     vprintf(const char *fmt, va_list ap);
int     vfprintf(void *stream, const char *fmt, va_list ap);
int     sprintf(char *out, const char *fmt, ...);
int     vsprintf(char *out, const char *fmt, va_list ap);
int     snprintf(char *out, size_t n, const char *fmt, ...);
int     vsnprintf(char *out, size_t n, const char *fmt, va_list ap);
int     puts(const char *s);
int     fputs(const char *s, void *stream);

/* 定时 */
int     nanosleep(const struct timespec *req, struct timespec *rem);
int     usleep(long us);
int     clock_gettime(int clk, struct timespec *ts);
int     gettimeofday(struct timeval *tv, void *tz);

/* 杂项 */
void    exit(int st);
void    _exit(int st);
int     isdigit(int c);
int     tolower(int c);

/* ----------------------- <linux/fb.h> ----------------------- */
struct fb_bitfield {
    uint32_t offset;
    uint32_t length;
    uint32_t msb_right;
};
struct fb_var_screeninfo {
    uint32_t xres;
    uint32_t yres;
    uint32_t xres_virtual;
    uint32_t yres_virtual;
    uint32_t xoffset;
    uint32_t yoffset;
    uint32_t bits_per_pixel;
    uint32_t grayscale;
    struct fb_bitfield red;
    struct fb_bitfield green;
    struct fb_bitfield blue;
    struct fb_bitfield transp;
    uint32_t nonstd;
    uint32_t activate;
    uint32_t height;
    uint32_t width;
    uint32_t accel_flags;
    uint32_t pixclock;
    uint32_t left_margin;
    uint32_t right_margin;
    uint32_t upper_margin;
    uint32_t lower_margin;
    uint32_t hsync_len;
    uint32_t vsync_len;
    uint32_t sync;
    uint32_t vmode;
    uint32_t rotate;
    uint32_t colorspace;
    uint32_t reserved[4];
};
#define FBIOGET_VSCREENINFO 0x4600
#define FBIOPUT_VSCREENINFO 0x4601
#define FBIOGET_FSCREENINFO 0x4602

/* ----------------------- <linux/input.h> ----------------------- */
struct input_event {
    struct timeval time;
    uint16_t type;
    uint16_t code;
    int32_t  value;
};
#define EV_SYN          0x00
#define EV_KEY          0x01
#define EV_REL          0x02
#define EV_ABS          0x03
#define ABS_X           0x00
#define ABS_Y           0x01
#define ABS_PRESSURE    0x18
#define ABS_MT_POSITION_X 0x35
#define ABS_MT_POSITION_Y 0x36
#define ABS_MT_PRESSURE   0x3a
#define BTN_TOUCH       0x14a
#define SYN_REPORT      0
#define SYN_MT_REPORT   2

/* ----------------------- <linux/videodev2.h> ----------------------- */
enum v4l2_buf_type {
    V4L2_BUF_TYPE_VIDEO_CAPTURE  = 1,
    V4L2_BUF_TYPE_VIDEO_OUTPUT   = 2,
    V4L2_BUF_TYPE_VIDEO_OVERLAY = 3,
};
enum v4l2_field {
    V4L2_FIELD_ANY     = 0,
    V4L2_FIELD_NONE    = 1,
};
enum v4l2_memory {
    V4L2_MEMORY_MMAP      = 1,
    V4L2_MEMORY_USERPTR   = 2,
    V4L2_MEMORY_OVERLAY   = 3,
};
/* fourcc */
#define V4L2_PIX_FMT_RGB332  0x32335252
#define V4L2_PIX_FMT_RGB565  0x50424752
#define V4L2_PIX_FMT_RGB24   0x33424752
#define V4L2_PIX_FMT_YUYV    0x56595559
#define V4L2_PIX_FMT_UYVY    0x59565955
#define V4L2_PIX_FMT_MJPEG   0x47504a4d  /* 'MJPG' */
#define V4L2_PIX_FMT_JPEG    0x4745504a  /* 'JPEG' */

struct v4l2_pix_format {
    uint32_t width;
    uint32_t height;
    uint32_t pixelformat;
    uint32_t field;
    uint32_t bytesperline;
    uint32_t sizeimage;
    uint32_t colorspace;
    uint32_t priv;
    uint32_t flags;
    uint32_t ycbcr_enc;
    uint32_t quantization;
    uint32_t xfer_func;
};
struct v4l2_format {
    uint32_t type;
    union {
        struct v4l2_pix_format pix;
        uint8_t raw[200];
    } fmt;
};
struct v4l2_timecode {
    uint32_t type;
    uint32_t flags;
    uint8_t  frames;
    uint8_t  seconds;
    uint8_t  minutes;
    uint8_t  hours;
    uint8_t  userbits[4];
};
/* 32-bit ARM 上 sizeof(v4l2_buffer) = 88 (0x58), 必须和内核一致 */
struct v4l2_buffer {
    uint32_t index;
    uint32_t type;
    uint32_t bytesused;
    uint32_t flags;
    uint32_t field;
    struct timeval timestamp;      /* off 20, 8 bytes */
    struct v4l2_timecode timecode; /* off 28, 16 bytes */
    uint32_t sequence;             /* off 44 */
    uint32_t memory;               /* off 48 */
    union {                        /* off 52 */
        uint32_t       offset;
        unsigned long  userptr;
        void          *planes;
        int            fd;
    } m;
    uint32_t length;               /* off 56 */
    uint32_t reserved2;            /* off 60 */
    uint32_t reserved;             /* off 64 */
    uint32_t _pad[5];              /* pad 到 88 字节 */
};
struct v4l2_capability {
    uint8_t  driver[16];
    uint8_t  card[32];
    uint8_t  bus_info[32];
    uint32_t version;
    uint32_t capabilities;
    uint32_t device_caps;
    uint32_t reserved[3];
};
struct v4l2_fmtdesc {
    uint32_t index;
    uint32_t type;
    uint32_t flags;
    uint8_t  description[32];
    uint32_t pixelformat;
    uint32_t reserved[4];
};
struct v4l2_frmsize_discrete { uint32_t width; uint32_t height; };
struct v4l2_frmsize_stepwise {
    uint32_t min_width;  uint32_t max_width;  uint32_t step_width;
    uint32_t min_height; uint32_t max_height; uint32_t step_height;
};
struct v4l2_frmsizeenum {
    uint32_t index;
    uint32_t pixel_format;
    uint32_t type;   /* 1=discrete 2=continuous 3=stepwise */
    union {
        struct v4l2_frmsize_discrete discrete;
        struct v4l2_frmsize_stepwise stepwise;
        uint8_t raw[24];
    };
    uint32_t reserved[2];
};
struct v4l2_requestbuffers {
    uint32_t count;
    uint32_t type;
    uint32_t memory;
    uint32_t reserved[2];
};

/* ioctl 号 (32-bit ARM, 已含正确 _IOC size) */
#define VIDIOC_QUERYCAP        0x80685600
#define VIDIOC_ENUM_FMT        0xc0405602
#define VIDIOC_G_FMT           0xc0cc5604
#define VIDIOC_S_FMT           0xc0cc5605
#define VIDIOC_REQBUFS         0xc0145608
#define VIDIOC_QUERYBUF        0xc0585609
#define VIDIOC_QBUF            0xc058560f
#define VIDIOC_DQBUF           0xc0585611
#define VIDIOC_STREAMON        0x40045612
#define VIDIOC_STREAMOFF       0x40045613
#define VIDIOC_ENUM_FRAMESIZES 0xc02c564a

#define V4L2_CAP_VIDEO_CAPTURE 0x00000001
#define V4L2_CAP_STREAMING     0x04000000
#define V4L2_BUF_FLAG_ERROR    0x0040

#endif /* LINUX_SHIM_H */
