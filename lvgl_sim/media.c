/* media.c -- JPEG/MJPEG 解码, 直接调用 TJpgDec 底层 API (jd_prepare/jd_decomp) */
#include "media.h"
#include "linux_shim.h"
#include "lvgl/src/libs/tjpgd/tjpgd.h"

/* TJPGD 工作池 (FASTDECODE=1 约需 3.1KB, 给 16KB 充裕) */
static uint8_t jd_pool[16 * 1024] __attribute__((aligned(8)));

typedef struct {
    const uint8_t *data;
    size_t size;
    size_t pos;
} mem_stream_t;

/* TJPGD 输入回调: buff==NULL 时跳过 ndata 字节, 否则拷贝 */
static size_t mem_infunc(JDEC *jd, uint8_t *buff, size_t ndata)
{
    mem_stream_t *s = (mem_stream_t *)jd->device;
    size_t avail = s->size - s->pos;
    if (ndata > avail) ndata = avail;
    if (buff) {
        const uint8_t *p = s->data + s->pos;
        for (size_t i = 0; i < ndata; i++) buff[i] = p[i];
    }
    s->pos += ndata;
    return ndata;
}

/* 解码输出参数, 传给 TJPGD 输出回调 */
typedef struct {
    uint8_t *buf;
    int stride;
} out_ctx_t;

/* prepare 和 decomp 阶段共用同一个 device:
 * 输入回调要读数据流, 输出回调要写缓冲, 所以打包在一起 */
typedef struct {
    mem_stream_t ms;
    out_ctx_t out;
} decode_ctx_t;

/* TJPGD 每解出一个 MCU 条带调用一次, 把 RGB888 矩形拷进目标缓冲 */
static int out_func(JDEC *jd, void *bitmap, JRECT *rect)
{
    decode_ctx_t *c = (decode_ctx_t *)jd->device;
    const uint8_t *src = (const uint8_t *)bitmap;
    int w = rect->right - rect->left + 1;
    for (int y = rect->top; y <= rect->bottom; y++) {
        uint8_t *dst = c->out.buf + (size_t)y * c->out.stride
                            + (size_t)rect->left * 3;
        for (int x = 0; x < w; x++) {
            dst[x*3+0] = src[x*3+0]; /* R */
            dst[x*3+1] = src[x*3+1]; /* G */
            dst[x*3+2] = src[x*3+2]; /* B */
        }
        src += (size_t)w * 3;
    }
    return 1; /* 继续解码 */
}

int media_decode_jpeg(const uint8_t *data, size_t size,
                      uint8_t *buf, int bufw, int bufh,
                      int *outw, int *outh)
{
    if (!data || size < 4 || !buf) return -1;

    decode_ctx_t c;
    c.ms.data = data; c.ms.size = size; c.ms.pos = 0;

    JDEC jd;
    JRESULT rc = jd_prepare(&jd, mem_infunc, jd_pool, sizeof(jd_pool), &c);
    if (rc != JDR_OK) {
        printf("[JPG] jd_prepare fail rc=%d\n", (int)rc);
        return -2;
    }

    /* 选缩放档: 0=原尺寸 1=1/2 2=1/4 3=1/8, 保证不超过缓冲 */
    int scale = 0;
    while (scale < 3) {
        int w = jd.width >> scale;
        int h = jd.height >> scale;
        if (w <= bufw && h <= bufh) break;
        scale++;
    }

    c.out.buf = buf;
    c.out.stride = bufw * 3;

    rc = jd_decomp(&jd, out_func, (uint8_t)scale);
    if (rc != JDR_OK) {
        printf("[JPG] jd_decomp fail rc=%d\n", (int)rc);
        return -3;
    }

    if (outw) *outw = jd.width >> scale;
    if (outh) *outh = jd.height >> scale;
    return 0;
}

int media_mjpeg_frame(const uint8_t *data, size_t size, int idx,
                      size_t *pstart, size_t *pend)
{
    int found = -1;
    size_t i = 0;
    size_t frame_start = (size_t)-1;
    int cur = -1;
    while (i + 1 < size) {
        if (data[i] == 0xFF && data[i+1] == 0xD8) {   /* SOI 帧起始 */
            frame_start = i;
            cur++;
            i += 2;
            continue;
        }
        if (data[i] == 0xFF && data[i+1] == 0xD9 && frame_start != (size_t)-1) { /* EOI */
            if (cur == idx) {
                *pstart = frame_start;
                *pend = i + 2;
                found = 0;
                break;
            }
            frame_start = (size_t)-1;
        }
        i++;
    }
    return found;
}

int media_map_file(const char *path, uint8_t **map, size_t *size_out)
{
    int fd = open(path, O_RDONLY, 0);
    if (fd < 0) return -1;
    long sz = lseek(fd, 0, 2 /*SEEK_END*/);
    if (sz <= 0) { close(fd); return -1; }
    lseek(fd, 0, 0 /*SEEK_SET*/);
    uint8_t *m = (uint8_t *)mmap(0, (size_t)sz, PROT_READ, MAP_PRIVATE, fd, 0);
    if (m == MAP_FAILED || m == 0) { close(fd); return -1; }
    *map = m;
    *size_out = (size_t)sz;
    return fd;
}
