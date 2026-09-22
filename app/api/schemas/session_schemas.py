# -*- coding: utf-8 -*-
"""会话相关 schema。

安全说明：anonymous_id 是服务端生成/校验的 UUID 形态标识，
不携带任何真实身份语义；客户端传入的 anonymous_id 仅做格式校验。
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from app.common.constants import PersonaType


class SessionCreateRequest(BaseModel):
    """POST /api/session 请求体（anonymous_id 可选，缺省服务端生成）。"""

    anonymous_id: str | None = Field(
        None, min_length=8, max_length=64, description="匿名用户标识（缺省自动生成）"
    )

    @field_validator("anonymous_id")
    @classmethod
    def anonymous_id_must_be_uuidish(cls, v: str | None) -> str | None:
        """格式校验：必须是合法 UUID（服务端只接受 UUID 形态，防注入任意字符串）。"""
        if v is None:
            return None
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError("anonymous_id 必须是合法 UUID") from exc
        return v


class SessionResponse(BaseModel):
    """会话创建响应。"""

    session_id: str
    anonymous_id: str
    persona_type: PersonaType = Field(..., description="初始画像（默认 P4）")
    crisis_hotline: str = Field(..., description="心理援助热线（创建即告知，安全兜底）")
    created_at: str
