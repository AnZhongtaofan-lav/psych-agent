# -*- coding: utf-8 -*-
"""
对话相关 schema（请求/响应模型）。

安全设计：
1. ChatRequest.content 在 schema 层做输入护栏校验（长度 + 控制字符），
   非法输入在进入逻辑层之前就被 422 拒绝（系统边界校验原则）
2. ChatResponse 只携带脱敏后的安全字段：
   - reply 来自本地模板或已安检的 LLM 输出
   - matched_lexicons 是词典标签（非用户原文）
   - 不存在任何可携带 PII 的自由文本字段
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from app.common.config import settings
from app.common.constants import EmotionSource, PersonaType, RiskLevel, SessionState

# 控制字符（除换行/回车/制表符外一律拒绝）：防日志伪造与终端注入
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ChatRequest(BaseModel):
    """POST /api/chat 请求体。"""

    session_id: str = Field(..., min_length=8, max_length=64, description="会话 ID")
    content: str = Field(
        ...,
        min_length=1,
        max_length=settings.max_input_length,
        description="用户输入（1~2000 字）",
    )
    anonymous_id: str | None = Field(
        None, min_length=8, max_length=64, description="匿名用户标识（可选校验）"
    )

    @field_validator("content")
    @classmethod
    def content_must_be_clean(cls, v: str) -> str:
        """输入护栏：拒绝控制字符注入，保留换行与制表（正常文本）。"""
        if _CONTROL_CHARS_RE.search(v):
            # 不回显具体字符，避免给绕过者反馈信息
            raise ValueError("输入内容包含非法字符")
        return v


class EmotionOut(BaseModel):
    """情绪识别结果（响应子结构）。"""

    category: str = Field(..., description="情绪类别（焦虑/抑郁/愤怒/悲伤/平静/中性）")
    intensity: float = Field(..., ge=0.0, le=1.0, description="强度 0~1")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 0~1")
    source: EmotionSource = Field(..., description="识别来源 rule/llm/rule+llm")


class RiskOut(BaseModel):
    """风险评估结果（响应子结构）。

    安全说明：matched_lexicons 为词典条目标签（如 "自杀意念:不想活"），
    来自固定词典而非用户文本，不构成 PII 泄露。
    """

    level: RiskLevel = Field(..., description="风险等级 0~3")
    label: str = Field(..., description="等级标签（正常/关注/高风险/危机）")
    is_intercepted: bool = Field(..., description="是否触发高危拦截")
    matched_lexicons: list[str] = Field(..., description="命中的词典条目标签")


class ChatResponse(BaseModel):
    """POST /api/chat 响应体。"""

    reply: str = Field(..., description="智能体回复（L3 时为拦截话术）")
    # 【脱敏回显】用户消息的服务端脱敏版本——前端展示用户气泡时
    # 只允许使用本字段，禁止回显本地原文（防 PII 暴露在屏幕/截屏场景）
    user_message: str = Field(
        ...,
        description="用户消息（服务端已脱敏的回显文本，前端唯一合法展示来源）",
    )
    emotion: EmotionOut
    risk: RiskOut
    persona: PersonaType = Field(..., description="本轮用户画像 P1~P4")
    crisis_hotline: str = Field(..., description="心理援助热线（始终返回，确保客户端可得）")
    session_state: SessionState = Field(..., description="会话当前状态")


class SessionEndResponse(BaseModel):
    """POST /api/session/{id}/end 响应体。"""

    session_id: str
    state: SessionState
