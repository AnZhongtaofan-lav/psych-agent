/* media.h -- JPEG/MJPEG 解码 (基于 LVGL 内置 TJpgDec), 供相册和视频播放调用 */
#ifndef MEDIA_H
#define MEDIA_H

#include <stdint.h>
#include <stddef.h>

/* 把整张 JPEG 解到 RGB888 缓冲区.
 * buf      : 输出缓冲 (w*h*3 字节, 由调用方保证)
 * bufw/bufh: 缓冲容量(像素); 实际图像按 TJPGD 1/2/4/8 缩放使其不超出
 * 返回: 0 成功, <0 失败; *outw/*outh 返回实际写入的图像宽高 */
int media_decode_jpeg(const uint8_t *data, size_t size,
                      uint8_t *buf, int bufw, int bufh,
                      int *outw, int *outh);

/* 在一整段 MJPEG 数据里找第 idx 帧 (从0开始) 的起止偏移.
 * 返回: 0 找到, -1 没有更多帧 */
int media_mjpeg_frame(const uint8_t *data, size_t size, int idx,
                      size_t *start, size_t *end);

/* 文件工具: 整个文件读进 mmap(只读), *map 返回地址, *size 大小.
 * 成功返回 fd(>=0, 用于结束后 munmap), 失败 -1 */
int media_map_file(const char *path, uint8_t **map, size_t *size);

#endif
