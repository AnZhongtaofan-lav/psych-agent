# -*- coding: utf-8 -*-
"""
输入护栏中间件 —— 请求体体积上限（第一道物理防线）。

职责分层说明（防线纵深设计）：
    1. 本中间件：请求体【字节体积】超限 → 413 直接拒绝
       （在 pydantic 解析前生效，防止超大 payload 消耗解析资源）
    2. schema 校验（chat_schemas.ChatRequest）：内容【长度上限】+ 控制字符
       → 422 拒绝（语义层护栏）
    两层独立生效，互为冗余。

安全说明：
    本中间件只读 Content-Length 头，不读取/记录请求体内容（无 PII 接触面）。
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.common.config import settings


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """拒绝 Content-Length 超限的请求（上限 = 输入长度上限 × 6 字节余量）。

    6 倍余量依据：UTF-8 中文每字符最多 3 字节，再留 JSON 转义余量；
    正常合法请求（≤2000 字）永远不会被误伤。
    """

    def __init__(self, app) -> None:  # noqa: ANN001 —— Starlette 签名
        super().__init__(app)
        self._max_bytes = settings.max_input_length * 6

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        # multipart/form-data（文件上传）跳过本中间件的字节限制：
        # 媒体文件上限由媒体路由自身（UploadFile + content-type 校验）严格守卫。
        # 本中间件只负责拦截意外的超大 JSON/纯文本 payload。
        content_type = request.headers.get("content-type", "").lower()
        if "multipart/form-data" in content_type:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None and content_length.isdigit():
            if int(content_length) > self._max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "请求体过大"},
                )
        return await call_next(request)
