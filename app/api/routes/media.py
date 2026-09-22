# -*- coding: utf-8 -*-
"""
媒体管理路由 —— 摄像头照片/录像的上传、列表、下载。

设计要点：
1. 存储在文件系统（data/media/photos/、data/media/videos/），绝不进 SQLite BLOB
2. 文件名统一用 UUID 重命名（前端文件名完全不可信）
3. Content-Type 严格白名单：照片 image/jpeg|image/png，视频 video/webm|video/mp4
4. 文件大小上限可配置（settings.max_photo_bytes / max_video_bytes）
5. 列表按 created_at 倒序（最新在最前），返回 JSON 不暴露文件系统绝对路径
6. 下载路由对文件名做路径穿越防护（只允许当前目录下的文件）
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.common.config import settings
from app.common.logger import get_logger

router = APIRouter(tags=["media"])
logger = get_logger(__name__)

# ---- 目录 ----
_PHOTO_DIR = Path(settings.media_dir) / "photos"
_VIDEO_DIR = Path(settings.media_dir) / "videos"


def ensure_media_dirs() -> None:
    """启动时创建媒体目录（幂等，main.py lifespan 调用）。"""
    _PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    _VIDEO_DIR.mkdir(parents=True, exist_ok=True)


# ---- 媒体类型常量 ----
class MediaType:
    PHOTO = "photo"
    VIDEO = "video"


# 类型 → 存储目录 + 允许的 MIME + 大小上限 + 扩展名
_MEDIA_RULES: dict[str, dict] = {
    MediaType.PHOTO: {
        "dir": _PHOTO_DIR,
        "allowed_mime": {"image/jpeg", "image/png"},
        "max_bytes": settings.max_photo_bytes,
        "ext_map": {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"},
        "default_ext": ".jpg",
    },
    MediaType.VIDEO: {
        "dir": _VIDEO_DIR,
        "allowed_mime": {"video/webm", "video/mp4"},
        "max_bytes": settings.max_video_bytes,
        "ext_map": {".webm": "video/webm", ".mp4": "video/mp4"},
        "default_ext": ".webm",
    },
}


def _resolve_rules(media_type: str) -> dict:
    if media_type not in _MEDIA_RULES:
        raise HTTPException(
            status_code=400, detail=f"不支持的媒体类型: {media_type}"
        )
    return _MEDIA_RULES[media_type]


def _sanitize_mime(uploaded: UploadFile, rules: dict) -> str:
    """MIME 严格校验。浏览器可能根据文件扩展名猜测 MIME，
    这里以 UploadFile.content_type（浏览器上报）为主、以文件扩展名做交叉确认。
    """
    reported = (uploaded.content_type or "").lower().strip()
    allowed = rules["allowed_mime"]
    if reported and reported not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型: {reported}。允许: {', '.join(sorted(allowed))}",
        )
    # 扩展名兜底
    orig = (uploaded.filename or "").lower()
    for ext, mt in rules["ext_map"].items():
        if orig.endswith(ext):
            if reported and reported != mt:
                raise HTTPException(
                    status_code=415,
                    detail=f"扩展名与 MIME 不匹配（{ext} vs {reported}）",
                )
            return mt
    # 没扩展名也没 MIME → 拒绝
    if not reported:
        raise HTTPException(status_code=415, detail="无法识别文件类型")
    if reported not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型: {reported}。允许: {', '.join(sorted(allowed))}",
        )
    return reported


def _save_file(uploaded: UploadFile, rules: dict, mime: str) -> dict:
    """保存上传文件：读取全部数据、校验大小、UUID 重命名落盘。

    注意：UploadFile.read() 一次性读入内存——
    对于 ≤50MB 的视频完全可接受（心理服务场景不产生大文件）。
    若后续有 ≥200MB 的视频需求，改用 StreamingUploadFile 分块写入。
    """
    data = uploaded.file.read()
    actual_size = len(data)
    if actual_size > rules["max_bytes"]:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{actual_size} 字节，上限 {rules['max_bytes']} 字节）",
        )

    # UUID 作为文件名（+扩展名），完全隔离前端文件名注入
    ext = rules["default_ext"]
    for e, mt in rules["ext_map"].items():
        if mt == mime:
            ext = e
            break
    safe_name = f"{uuid.uuid4().hex}{ext}"
    target = rules["dir"] / safe_name

    # 二次安全：目标路径必须在指定目录下（防目录穿越）
    if not target.resolve().is_relative_to(rules["dir"].resolve()):
        raise HTTPException(status_code=400, detail="非法路径")

    target.write_bytes(data)

    return {
        "filename": safe_name,
        "size": actual_size,
        "mime": mime,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


# ============================================================
# 路由
# ============================================================

@router.post("/media/upload")
async def upload(
    media_type: str = Form(...),
    file: UploadFile = File(...),
) -> JSONResponse:
    """上传一张照片或一段录像。

    - media_type: "photo" 或 "video"
    - file: multipart 表单字段
    """
    rules = _resolve_rules(media_type)
    mime = _sanitize_mime(file, rules)
    meta = _save_file(file, rules, mime)

    logger.info(
        "媒体上传成功: type=%s, filename=%s, size=%d",
        media_type, meta["filename"], meta["size"],
    )
    return JSONResponse(status_code=201, content={"ok": True, **meta})


@router.get("/media/list/{media_type}")
def list_media(media_type: str) -> list[dict]:
    """列出指定类型的所有媒体文件（按创建时间倒序）。"""
    rules = _resolve_rules(media_type)
    files = []
    for f in sorted(rules["dir"].iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file():
            mime = mimetypes.guess_type(f.name)[0] or rules["default_ext"]
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "mime": mime,
                "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(
                    timespec="seconds"
                ),
            })
    return files


@router.get("/media/{media_type}/{filename}")
def download(media_type: str, filename: str):
    """下载/预览媒体文件。

    路径穿越防护：
    1. 文件名不允许包含路径分隔符
    2. resolve() 后必须在目标目录内
    """
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    rules = _resolve_rules(media_type)
    target = (rules["dir"] / filename).resolve()

    if not target.is_relative_to(rules["dir"].resolve()):
        raise HTTPException(status_code=400, detail="非法路径")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=mime, filename=target.name)


@router.delete("/media/{media_type}/{filename}")
def delete(media_type: str, filename: str) -> dict:
    """删除指定媒体文件（同样的路径穿越防护）。"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    rules = _resolve_rules(media_type)
    target = (rules["dir"] / filename).resolve()
    if not target.is_relative_to(rules["dir"].resolve()):
        raise HTTPException(status_code=400, detail="非法路径")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    target.unlink()
    logger.info("媒体已删除: type=%s, filename=%s", media_type, filename)
    return {"ok": True, "filename": filename}
