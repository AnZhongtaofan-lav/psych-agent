# -*- coding: utf-8 -*-
"""画像查询 schema。

安全红线（结构性防泄露）：
    响应字段全部为受控枚举/数值/类别名聚合，【没有任何自由文本字段】，
    即使数据层未来意外混入 PII，该接口的结构也无法将其输出。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.common.constants import PersonaType


class ProfileResponse(BaseModel):
    """GET /api/profile/{anonymous_id} 响应体（输出即脱敏设计）。"""

    anonymous_id: str = Field(..., description="匿名用户标识（UUID）")
    persona_type: PersonaType = Field(..., description="当前画像")
    dominant_emotions: dict[str, float] = Field(
        ..., description="情绪强度分布（EMA 聚合，键为受控类别名）"
    )
    mood_trend: list[str] = Field(..., description="最近情绪类别序列（≤20 条）")
    risk_level_max: int = Field(..., ge=0, le=3, description="历史最高风险等级")
    risk_streak: int = Field(..., ge=0, description="当前连续高危轮数")
    interaction_count: int = Field(..., ge=0, description="累计对话轮数")
