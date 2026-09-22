# -*- coding: utf-8 -*-
"""
业务异常体系。

设计原则：
1. 业务异常统一继承 AppException，携带 HTTP 状态码与用户可见消息
2. 消息面向用户必须安全：不得泄露内部实现（如 SQL 错误、堆栈、路径）
3. 交互层全局异常处理器捕获 AppException 转为 JSON 响应；
   未预期异常一律 500 + 通用文案，原始堆栈只进日志（且日志不含用户原文）
"""

from __future__ import annotations


class AppException(Exception):
    """业务异常基类。

    属性:
        status_code: 映射的 HTTP 状态码
        message: 用户可见的安全文案（不含内部细节）
    """

    status_code: int = 500
    message: str = "服务内部错误，请稍后重试"

    def __init__(self, message: str | None = None, status_code: int | None = None) -> None:
        # 允许子类实例化时覆盖默认文案与状态码
        if message is not None:
            self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class SessionNotFoundError(AppException):
    """会话不存在或已结束：HTTP 404。

    安全说明：404 语义只表达"不可用"，不区分"从未存在"与"已删除"，
    避免泄露会话存在性信息。
    """

    status_code = 404
    message = "会话不存在或已结束"


class ProfileNotFoundError(AppException):
    """画像不存在：HTTP 404（同样不泄露存在性之外的信息）。"""

    status_code = 404
    message = "用户画像不存在"


class InputTooLongError(AppException):
    """输入超出长度上限：HTTP 422（由交互层输入护栏抛出）。"""

    status_code = 422
    message = "输入内容超出长度限制"


class InvalidInputError(AppException):
    """输入包含非法内容（如控制字符注入）：HTTP 422。"""

    status_code = 422
    message = "输入内容包含非法字符"
