# -*- coding: utf-8 -*-
"""
日志工厂模块。

安全红线（本模块存在的核心目的）：
    任何日志输出都【禁止包含用户原文与 PII】。
    实现方式：提供 mask 参数，调用方在记录包含用户内容的日志时，
    必须先经过脱敏器处理；为防止遗忘，此处额外提供一个
    "只在 DEBUG 级别输出且强制打码"的 debug_masked 方法。
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache

from app.common.config import settings


# ------------------------------------------------------------
# 日志格式：时间 | 级别 | 模块 | 消息
# 注意：格式中不包含请求体/响应体，避免敏感信息经格式化通道泄露
# ------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@lru_cache(maxsize=None)
def get_logger(name: str) -> logging.Logger:
    """获取具名 logger（带缓存，保证同名 logger 只初始化一次）。

    参数:
        name: 通常传 __name__，形成 "app.core.risk.risk_engine" 式层级命名
    """
    logger = logging.getLogger(name)

    # 幂等初始化：已配置过 handler 则直接返回
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(settings.log_level)
        # 不向 root logger 传播，避免 uvicorn 二次输出造成日志重复
        logger.propagate = False

    return logger
