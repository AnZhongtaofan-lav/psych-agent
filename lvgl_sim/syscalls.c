/* ============================================================
 * syscalls.c — GEC6818 ARM Linux (裸机 syscall) 微型 C runtime
 *
 * 不依赖 newlib/libc：用内联汇编 swi 0x900000 直接发 Linux ARM EABI
 * syscall。提供 LVGL + main_board.c 所需的全部 C 运行时符号：
 *
 *   - 文件 I/O : open close read write lseek ioctl
 *   - 内存映射 : mmap (mmap2) munmap
 *   - I/O 多路: select
 *   - 定时    : usleep (nanosleep) clock_gettime
 *   - 内存    : malloc/free/calloc/realloc (bump allocator)
 *   - 字符串  : memset memcpy memmove memcmp strlen strcpy strncpy strcmp strchr
 *   - 格式化  : printf snprintf (简化版: %d %u %x %X %s %c %% p)
 *   - 杂项    : strerror exit _exit _start
 *
 * 编译:
 *   arm-none-eabi-gcc -c syscalls.c -O2 -o syscalls.o
 *   arm-none-eabi-gcc -e _start -nostdlib -nostartfiles -static \
 *       syscalls.o main_board.o <lvgl *.o> -o gec6818_app
 * ============================================================ */

/* ----------------------- 基本类型: 用编译器自带头 ----------------------- */
#include <stdint.h>
#include <stddef.h>

typedef long                ssize_t;  /* 编译器没 ssize_t, 自己定义 */
typedef long                off_t;   /* 同上 */
typedef int                 pid_t;
typedef unsigned int        uint;

/* ----------------------- O_* / PROT_* / MAP_* ----------------------- */
#define O_RDONLY       0
#define O_WRONLY       1
#define O_RDWR         2
#define O_CREAT      0100
#define O_EXCL       0200
#define O_TRUNC      01000
#define O_APPEND     02000
#define O_NONBLOCK   04000

#define PROT_READ      0x1
#define PROT_WRITE     0x2
#define PROT_EXEC      0x4
#define PROT_NONE      0x0

#define MAP_SHARED     0x01
#define MAP_PRIVATE    0x02
#define MAP_FIXED     0x10
#define MAP_ANONYMOUS 0x20
#define MAP_FAILED     ((void*)-1)

/* ----------------------- errno 桩 ----------------------- */
int errno_dummy;
#define errno errno_dummy

/* ----------------------- Linux ARM EABI syscall 号 ----------------------- */
/* swi 0x900000  | r7=号 | r0..r5=参数 | 返回 r0 */
#define SYS_exit           1
#define SYS_read           3
#define SYS_write          4
#define SYS_open           5
#define SYS_close          6
#define SYS_lseek         19
#define SYS_brk          45
#define SYS_ioctl        54
#define SYS_gettimeofday 78
#define SYS_select      142
#define SYS_nanosleep   162
#define SYS_clock_gettime 263
#define SYS_mmap2       192
#define SYS_munmap       91

/* ----------------------- 内联汇编 syscall ----------------------- */
/* 5 参数版本 (r0..r3, r4, r7) — 用于 ioctl/select/nanosleep 等.
 * 关键: r4 是 ARM EABI 的被调用者保存寄存器, 我们往里写第 5 个参数,
 * 必须声明成 "+r"(读写), 否则 GCC 以为 r4 不变, open/ioctl 返回后会
 * 用到被破坏的旧值 -> 野指针段错误. */
static inline long _swi5(int n, long a1, long a2, long a3, long a4, long a5) {
    register long r0 __asm__("r0") = a1;
    register long r1 __asm__("r1") = a2;
    register long r2 __asm__("r2") = a3;
    register long r3 __asm__("r3") = a4;
    register long r4 __asm__("r4") = a5;
    register long r7 __asm__("r7") = n;
    __asm__ volatile("swi 0x900000"
                     : "+r"(r0), "+r"(r4)
                     : "r"(r1), "r"(r2), "r"(r3), "r"(r7)
                     : "memory", "cc");
    return r0;
}

/* 6 参数版本 (r0..r5, r7) — 仅 mmap2 用. r4/r5 都要声明成 "+r". */
static inline long _swi6(int n, long a1, long a2, long a3, long a4, long a5, long a6) {
    register long r0 __asm__("r0") = a1;
    register long r1 __asm__("r1") = a2;
    register long r2 __asm__("r2") = a3;
    register long r3 __asm__("r3") = a4;
    register long r4 __asm__("r4") = a5;
    register long r5 __asm__("r5") = a6;
    register long r7 __asm__("r7") = n;
    __asm__ volatile("swi 0x900000"
                     : "+r"(r0), "+r"(r4), "+r"(r5)
                     : "r"(r1), "r"(r2), "r"(r3), "r"(r7)
                     : "memory", "cc");
    return r0;
}

/* ----------------------- 文件 I/O ----------------------- */
int open(const char *p, int f, int m) {
    (void)m;
    return (int)_swi5(SYS_open, (long)p, f, 0, 0, 0);
}
int close(int fd) {
    return (int)_swi5(SYS_close, fd, 0, 0, 0, 0);
}
ssize_t read(int fd, void *b, size_t n) {
    return _swi5(SYS_read, fd, (long)b, n, 0, 0);
}
ssize_t write(int fd, const void *b, size_t n) {
    return _swi5(SYS_write, fd, (long)b, n, 0, 0);
}
off_t lseek(int fd, off_t o, int w) {
    return _swi5(SYS_lseek, fd, o, w, 0, 0);
}

/* ioctl 三个参数: fd, request, arg (指针或整型) */
int ioctl(int fd, unsigned long req, void *arg) {
    return (int)_swi5(SYS_ioctl, fd, req, (long)arg, 0, 0);
}

/* select: n, rfds, wfds, efds, tv (5 个参数, tv 在 r4) */
int select(int n, void *r, void *w, void *e, void *t) {
    return (int)_swi5(SYS_select, n, (long)r, (long)w, (long)e, (long)t);
}

/* ----------------------- 内存映射 ----------------------- */
void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    /* mmap2 的 offset 单位是 PAGE = 4096 */
    return (void *)_swi6(SYS_mmap2,
                         (long)addr, (long)len, prot, flags, fd, off >> 12);
}
int munmap(void *addr, size_t len) {
    return (int)_swi5(SYS_munmap, (long)addr, (long)len, 0, 0, 0);
}

/* mkdir(path, mode) — ARM EABI syscall 39 */
int mkdir(const char *path, uint32_t mode) {
    return (int)_swi5(39, (long)path, (long)mode, 0, 0, 0);
}

/* signal(sig, handler) — ARM EABI syscall 48. SIG_IGN=1 */
typedef void (*sighandler_t)(int);
sighandler_t signal(int sig, sighandler_t h) {
    return (sighandler_t)_swi5(48, sig, (long)h, 0, 0, 0);
}

/* ----------------------- 定时 ----------------------- */
struct timespec { long tv_sec; long tv_nsec; };
int nanosleep(const struct timespec *req, struct timespec *rem) {
    return (int)_swi5(SYS_nanosleep, (long)req, (long)rem, 0, 0, 0);
}
int usleep(long us) {
    struct timespec ts;
    ts.tv_sec  = us / 1000000;
    ts.tv_nsec = (us % 1000000) * 1000;
    return nanosleep(&ts, 0);
}
/* clock_gettime: clk_id 在 r0, ts 在 r1 */
#define CLOCK_REALTIME      0
#define CLOCK_MONOTONIC     1
int clock_gettime(int clk, struct timespec *ts) {
    return (int)_swi5(SYS_clock_gettime, clk, (long)ts, 0, 0, 0);
}

/* gettimeofday 兜底 (struct timeval { long tv_sec; long tv_usec }) */
struct timeval { long tv_sec; long tv_usec; };
int gettimeofday(struct timeval *tv, void *tz) {
    return (int)_swi5(SYS_gettimeofday, (long)tv, (long)tz, 0, 0, 0);
}

/* ----------------------- exit / _exit / _start ----------------------- */
void _exit(int st) { _swi5(SYS_exit, st, 0, 0, 0, 0); while(1); }
void  exit(int st) { _swi5(SYS_exit, st, 0, 0, 0, 0); while(1); }

/* Linux ELF 静态进程入口: 内核在栈上放 argc, argv[0..argc-1], NULL, envp..., NULL, auxv... */
extern int main(int argc, char **argv);
__attribute__((naked, noreturn))
void _start(void) {
    __asm__ volatile(
        "mov r0, sp          \n"   /* r0 = &argc          */
        "ldr r1, [r0], #4    \n"   /* r1 = argc, r0 = &argv[0] */
        "mov r2, r0          \n"   /* r2 = argv           */
        "bl  main            \n"
        "mov r4, r0          \n"   /* exit code in r4    */
        "mov r7, #1          \n"   /* SYS_exit = 1       */
        "swi 0x900000        \n"
        "1: b 1b             \n"
        :
        :
        : "memory");
    __builtin_unreachable();
}

/* ----------------------- 内存分配 (bump allocator) ----------------------- */
/* LVGL 内部用 LV_STDLIB_BUILTIN 自带的 lv_malloc/lv_free，不调用我们的 malloc。
 * main_board.c 会调用 malloc/free；这里给一个简单的 bump heap，足够初始化 1 个
 * framebuffer 大小的显存 (800*480*4 ≈ 1.5MB)。 */
static unsigned char __heap[4 * 1024 * 1024] __attribute__((aligned(8)));
static size_t __heap_off = 0;

void *malloc(size_t n) {
    size_t a = (n + 7) & ~7u;
    if (__heap_off + a > sizeof(__heap)) return 0;
    void *p = &__heap[__heap_off];
    __heap_off += a;
    return p;
}
void free(void *p) { (void)p; }
void *calloc(size_t n, size_t s) {
    size_t total = n * s;
    void *p = malloc(total);
    if (p) {
        unsigned char *b = p;
        for (size_t i = 0; i < total; i++) b[i] = 0;
    }
    return p;
}
void *realloc(void *p, size_t n) {
    if (!p) return malloc(n);
    if (n == 0) { free(p); return 0; }
    /* 简单实现: 分新块复制 (不保留旧块)。 */
    void *np = malloc(n);
    if (np) {
        unsigned char *d = np;
        const unsigned char *s = p;
        /* 不知旧大小, 拷 n 字节 (可能越界读旧块, 但 bump heap 末尾有 padding) */
        for (size_t i = 0; i < n; i++) d[i] = s[i];
    }
    return np;
}

/* ----------------------- 内存操作 ----------------------- */
void *memset(void *s, int c, size_t n) {
    unsigned char *p = (unsigned char *)s;
    while (n--) *p++ = (unsigned char)c;
    return s;
}
void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *dd = (unsigned char *)d;
    const unsigned char *ss = (const unsigned char *)s;
    while (n--) *dd++ = *ss++;
    return d;
}
void *memmove(void *d, const void *s, size_t n) {
    unsigned char *dd = (unsigned char *)d;
    const unsigned char *ss = (const unsigned char *)s;
    if (dd < ss) {
        while (n--) *dd++ = *ss++;
    } else {
        dd += n; ss += n;
        while (n--) *--dd = *--ss;
    }
    return d;
}
int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *aa = a, *bb = b;
    while (n--) { if (*aa != *bb) return *aa - *bb; aa++; bb++; }
    return 0;
}

/* ----------------------- 字符串 ----------------------- */
size_t strlen(const char *s) { const char *p = s; while (*p) p++; return p - s; }
char *strcpy(char *d, const char *s) {
    char *r = d; while ((*d++ = *s++)); return r;
}
char *strncpy(char *d, const char *s, size_t n) {
    size_t i = 0;
    for (; i < n && s[i]; i++) d[i] = s[i];
    for (; i < n; i++) d[i] = 0;
    return d;
}
char *strcat(char *d, const char *s) {
    char *r = d;
    while (*d) d++;
    while ((*d++ = *s++));
    return r;
}
char *strncat(char *d, const char *s, size_t n) {
    char *r = d;
    while (*d) d++;
    while (n-- && *s) *d++ = *s++;
    *d = 0;
    return r;
}
char *strstr(const char *h, const char *n) {
    if (!*n) return (char *)h;
    for (; *h; h++) {
        const char *a = h, *b = n;
        while (*a && *b && *a == *b) { a++; b++; }
        if (!*b) return (char *)h;
    }
    return 0;
}
char *strdup(const char *s) {
    size_t n = strlen(s) + 1;
    char *p = malloc(n);
    if (p) memcpy(p, s, n);
    return p;
}
int strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}
int strncmp(const char *a, const char *b, size_t n) {
    while (n-- && *a && *a == *b) { a++; b++; }
    if (n == (size_t)-1) return 0;
    return (unsigned char)*a - (unsigned char)*b;
}
char *strchr(const char *s, int c) {
    while (*s && *s != (char)c) s++;
    return *s == (char)c ? (char *)s : 0;
}
char *strrchr(const char *s, int c) {
    const char *last = 0;
    while (*s) { if (*s == (char)c) last = s; s++; }
    return (char *)last;
}
int isdigit(int c) { return c >= '0' && c <= '9'; }
int tolower(int c) { return (c >= 'A' && c <= 'Z') ? c + 32 : c; }

/* strerror: 板子没 locale, 直接给个固定串 */
char *strerror(int err) {
    (void)err;
    return "(err)";
}

/* ----------------------- 简单 printf / snprintf ----------------------- */
/* 支持: %d %i %u %x %X %s %c %p %%  + 长度前缀 l/ll */
static void out_char(char **p, const char *end, char c) {
    if (!*p) return;
    if (end && *p >= end) return;
    *(*p)++ = c;
}
static void out_str(char **p, const char *end, const char *s) {
    if (!s) s = "(null)";
    while (*s) out_char(p, end, *s++);
}
static void out_uint(char **p, const char *end, unsigned long v, unsigned base, int upper) {
    char buf[32];
    int i = 0;
    const char *digits = upper ? "0123456789ABCDEF" : "0123456789abcdef";
    if (!v) buf[i++] = '0';
    while (v) { buf[i++] = digits[v % base]; v /= base; }
    while (i > 0) out_char(p, end, buf[--i]);
}
static void out_int(char **p, const char *end, long v) {
    if (v < 0) { out_char(p, end, '-'); v = -v; }
    out_uint(p, end, (unsigned long)v, 10, 0);
}

typedef __builtin_va_list va_list;
#define va_start(ap, last) __builtin_va_start(ap, last)
#define va_end(ap)        __builtin_va_end(ap)
#define va_arg(ap, t)     __builtin_va_arg(ap, t)

static int vfmt(char **p, const char *end, const char *fmt, va_list ap) {
    while (*fmt) {
        if (*fmt != '%') { out_char(p, end, *fmt++); continue; }
        fmt++;
        int is_long = 0;
        /* 跳过标志和宽度: %-+ #0 及数字宽度, '.'精度; '*' 要吃掉一个 int 参数 */
        for (;;) {
            char c = *fmt;
            if (c == '-' || c == '+' || c == ' ' || c == '#' || c == '0') { fmt++; continue; }
            if (c >= '1' && c <= '9') { while (*fmt >= '0' && *fmt <= '9') fmt++; continue; }
            if (c == '.') { fmt++; while (*fmt >= '0' && *fmt <= '9') fmt++; continue; }
            if (c == '*') { fmt++; (void)va_arg(ap, int); continue; }
            break;
        }
        while (*fmt == 'l') { is_long++; fmt++; }
        switch (*fmt++) {
        case 'd': case 'i': {
            long v = is_long ? va_arg(ap, long) : (long)va_arg(ap, int);
            out_int(p, end, v); break;
        }
        case 'u': {
            unsigned long v = is_long ? va_arg(ap, unsigned long) : (unsigned long)va_arg(ap, unsigned int);
            out_uint(p, end, v, 10, 0); break;
        }
        case 'x': {
            unsigned long v = is_long ? va_arg(ap, unsigned long) : (unsigned long)va_arg(ap, unsigned int);
            out_uint(p, end, v, 16, 0); break;
        }
        case 'X': {
            unsigned long v = is_long ? va_arg(ap, unsigned long) : (unsigned long)va_arg(ap, unsigned int);
            out_uint(p, end, v, 16, 1); break;
        }
        case 's': out_str(p, end, va_arg(ap, const char *)); break;
        case 'c': out_char(p, end, (char)va_arg(ap, int)); break;
        case 'p': {
            out_char(p, end, '0'); out_char(p, end, 'x');
            unsigned long v = (unsigned long)va_arg(ap, void *);
            out_uint(p, end, v, 16, 0); break;
        }
        case '%': out_char(p, end, '%'); break;
        default: out_char(p, end, '?'); break;
        }
    }
    out_char(p, end, 0);
    return 0;
}

int printf(const char *fmt, ...) {
    char buf[512];
    char *p = buf;
    va_list ap; va_start(ap, fmt);
    vfmt(&p, buf + sizeof(buf), fmt, ap);
    va_end(ap);
    /* 直接 write 到 stdout (fd=1) */
    size_t n = p - buf - 1;  /* 不算末尾 \0 */
    write(1, buf, n);
    return (int)n;
}
int vprintf(const char *fmt, va_list ap) {
    char buf[512];
    char *p = buf;
    vfmt(&p, buf + sizeof(buf), fmt, ap);
    size_t n = p - buf - 1;
    write(1, buf, n);
    return (int)n;
}
int vfprintf(void *stream, const char *fmt, va_list ap) {
    char buf[512];
    char *p = buf;
    vfmt(&p, buf + sizeof(buf), fmt, ap);
    size_t n = p - buf - 1;
    write((int)(long)stream, buf, n);
    return (int)n;
}
int sprintf(char *out, const char *fmt, ...) {
    char *p = out;
    va_list ap; va_start(ap, fmt);
    vfmt(&p, 0, fmt, ap);
    va_end(ap);
    return (int)(p - out - 1);
}
int vsprintf(char *out, const char *fmt, va_list ap) {
    char *p = out;
    vfmt(&p, 0, fmt, ap);
    return (int)(p - out - 1);
}
int snprintf(char *out, size_t n, const char *fmt, ...) {
    char *p = out;
    va_list ap; va_start(ap, fmt);
    vfmt(&p, out + n, fmt, ap);
    va_end(ap);
    return (int)(p - out - 1);
}
int vsnprintf(char *out, size_t n, const char *fmt, va_list ap) {
    char *p = out;
    vfmt(&p, out + n, fmt, ap);
    return (int)(p - out - 1);
}

/* puts / fputs 给一些遗留代码用 */
int puts(const char *s) {
    size_t n = strlen(s);
    write(1, s, n);
    write(1, "\n", 1);
    return 0;
}
int fputs(const char *s, void *stream) {
    size_t n = strlen(s);
    write((int)(long)stream, s, n);
    return 0;
}
