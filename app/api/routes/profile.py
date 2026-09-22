# -*- coding: utf-8 -*-
"""
画像查询路由 —— GET /api/profile/{anonymous_id}。

安全设计（输出即脱敏）：
- 响应模型 ProfileResponse 结构上不含任何自由文本字段
- 404 语义：画像不存在与匿名 id 非法返回相同错误，
  不泄露"是否存在"之外的信息
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.api.dependencies import Services, provide_services
from app.api.schemas.profile_schemas import ProfileResponse
from app.common.constants import PersonaType
from app.common.exceptions import ProfileNotFoundError

router = APIRouter(tags=["profile"])


@router.get("/profile/{anonymous_id}", response_model=ProfileResponse)
def get_profile(
    anonymous_id: str,
    services: Services = Depends(provide_services),
) -> ProfileResponse:
    """查询匿名用户画像（仅统计字段，结构上不可能输出 PII）。"""
    # UUID 格式预检：非法格式直接 404（不进入数据库查询）
    try:
        uuid.UUID(anonymous_id)
    except ValueError as exc:
        raise ProfileNotFoundError() from exc

    profile = services.profiles.get(anonymous_id)
    if profile is None:
        raise ProfileNotFoundError()

    return ProfileResponse(
        anonymous_id=profile.anonymous_id,
        persona_type=profile.persona_type,  # type: ignore[arg-type]
        dominant_emotions=json.loads(profile.dominant_emotions),
        mood_trend=json.loads(profile.mood_trend),
        risk_level_max=profile.risk_level_max,
        risk_streak=profile.risk_streak,
        interaction_count=profile.interaction_count,
    )
