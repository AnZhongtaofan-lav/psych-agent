# -*- coding: utf-8 -*-
"""
访问日志中间件 —— 全链路"无 PII 日志"的实现点。

安全红线（本模块存在的意义）：
    访问日志只允许记录：方法、路径模板、状态码、耗时。
    【禁止】记录：请求体、响应体、查询字符串（三者都可能含用户原文/PII）。

    路径说明：本系统路由路径只含服务端生成的 UUID，
    不含用户可控文本，因此记录 path 不构成 PII 风险；
    若未来新增含用户参数的路径，必须先过 anonymizer 再落日志。

    若未来确需扩展日志字段（如 header 采样），扩展点必须：
    from app.storage.anonymizer import anonymize_strict
    field = anonymize_strict(raw_field)   # 写出前强制脱敏
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.common.logger import get_logger

logger = get_logger("app.api.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """结构化访问日志（无正文、无查询串、无 header）。"""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        # 只输出安全字段（见模块 docstring 的字段白名单）
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,  # 路径模板，无用户可控文本
            response.status_code,
            duration_ms,
        )
        return response
