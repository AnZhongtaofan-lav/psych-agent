# -*- coding: utf-8 -*-
"""
POST /api/chat —— 核心对话路由（全链路编排点）。

处理流水线（每一轮对话的完整生命周期）：
    1. 会话校验（存在性 + 状态机）
    2. 风险评估（规则 + 可选 LLM，max 融合）
    3. 画像推断（P3 强制优先）
    4. 情绪识别（规则 + 可选 LLM，置信度竞争）
    5. 对话策略决策（L3 → 拦截覆盖）
    6. 持久化（消息落库自动脱敏、风险事件、画像与会话更新）
    7. 组装响应（结构性无 PII）

安全时序说明：
    风险评估【先于】画像推断 —— P3 判定依赖本轮风险等级；
    拦截话术【先于】一切持久化决策前的最终回复 —— 保证落库的
    assistant 消息与返回给用户的回复完全一致（可审计）。
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.api.dependencies import Services, provide_services
from app.api.schemas.chat_schemas import ChatRequest, ChatResponse, EmotionOut, RiskOut
from app.common.constants import (
    ACTION_GUIDE,
    ACTION_INTERCEPT_HOTLINE,
    ACTION_MEDICAL,
    ACTION_NORMAL,
    MessageRole,
    RiskLevel,
    SessionState,
)
from app.common.exceptions import SessionNotFoundError
from app.common.logger import get_logger
from app.core.normalizer import normalize
from app.core.profile.profile_builder import (
    build_profile_update,
    extract_signals,
    infer_persona,
)
from app.storage.anonymizer import anonymize_strict
from app.storage.models import Message, RiskEvent

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)

# 会话的"可对话"状态白名单：终止态一律 404（不泄露终止原因给客户端）
_CHATABLE_STATES = {SessionState.ACTIVE.value, SessionState.CRISIS_WATCH.value}


def _action_to_const(action: str) -> str:
    """策略动作字符串 → 常量（幂等映射，仅用于类型收敛）。"""
    return {
        "normal": ACTION_NORMAL,
        "guide": ACTION_GUIDE,
        "medical": ACTION_MEDICAL,
        "intercept_hotline": ACTION_INTERCEPT_HOTLINE,
    }.get(action, ACTION_NORMAL)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request, services: Services = Depends(provide_services)) -> ChatResponse:
    """核心对话端点。"""
    # ---- 1. 会话校验 ----
    session = services.sessions.get(payload.session_id)
    if session is None or session.state not in _CHATABLE_STATES:
        # 404 不区分"不存在"与"已终止"，避免泄露会话状态信息
        raise SessionNotFoundError()
    if payload.anonymous_id is not None and payload.anonymous_id != session.anonymous_id:
        # 匿名 id 不匹配视为越权访问（同 404 处理，不暴露差异）
        raise SessionNotFoundError()

    # ---- 2. 风险评估（安全关键路径，最先执行） ----
    risk = services.risk_engine.assess(payload.content)

    # ---- 3. 画像推断（P3 强制优先，依赖本轮风险等级与历史标记） ----
    profile = services.profiles.get_or_create(session.anonymous_id)
    normalized = normalize(payload.content)
    persona = infer_persona(normalized, risk.level, profile.risk_level_max)

    # ---- 4. 情绪识别 ----
    emotion = services.emotion_engine.analyze(payload.content)

    # ---- 5. 对话策略决策（L3 → 拦截器覆盖回复） ----
    signals = extract_signals(normalized, persona)
    outcome = services.strategy.decide(
        risk=risk,
        emotion=emotion,
        persona=persona,
        user_text=payload.content,
        signals=signals,
        current_streak=session.risk_streak,
    )

    # ---- 6. 持久化（消息落库时由仓储层强制脱敏） ----
    now_user = Message(
        message_id=str(uuid.uuid4()),
        session_id=session.session_id,
        role=MessageRole.USER.value,
        content=payload.content,  # 仓储层写入前强制脱敏
        emotion_category=emotion.category.value,
        emotion_intensity=emotion.intensity,
        emotion_confidence=emotion.confidence,
        emotion_source=emotion.source.value,
        matched_rules=json.dumps(risk.matched_lexicons, ensure_ascii=False),
    )
    services.messages.add(now_user)

    services.messages.add(
        Message(
            message_id=str(uuid.uuid4()),
            session_id=session.session_id,
            role=MessageRole.ASSISTANT.value,
            content=outcome.reply,  # 拦截话术/模板/已安检 LLM 输出
        )
    )

    # 风险事件流水（安全审计核心表）
    services.risk_events.add(
        RiskEvent(
            event_id=str(uuid.uuid4()),
            session_id=session.session_id,
            risk_level=risk.level.value,
            triggered_lexicons=json.dumps(risk.matched_lexicons, ensure_ascii=False),
            is_intercepted=outcome.is_intercepted,
            action_taken=_action_to_const(outcome.action_taken),
        )
    )

    # 画像聚合更新（EMA / trend / streak / max）
    update = build_profile_update(
        profile_json_emotions=profile.dominant_emotions,
        profile_json_trend=profile.mood_trend,
        current_risk_max=profile.risk_level_max,
        current_streak=profile.risk_streak,
        emotion_category=emotion.category,
        emotion_intensity=emotion.intensity,
        risk_level=risk.level,
        persona=persona,
    )
    services.profiles.update(
        session.anonymous_id,
        dominant_emotions=json.loads(update["dominant_emotions"]),
        mood_trend=json.loads(update["mood_trend"]),
        risk_level_max=update["risk_level_max"],
        risk_streak=update["risk_streak"],
        persona_type=update["persona_type"],
        interaction_delta=1,
    )

    # 会话元数据更新（streak / state / persona）
    new_state = outcome.new_state if outcome.new_state is not None else SessionState(session.state)
    services.sessions.update_after_round(
        session.session_id,
        persona_type=persona.value,
        risk_streak=outcome.new_streak,
        risk_level_max=max(session.risk_level_max, risk.level.value),
        state=new_state.value,
    )

    if outcome.is_intercepted:
        # 拦截事件记入安全日志（不含用户原文，仅等级与动作）
        logger.warning(
            "高危拦截触发: session=..., level=%d, action=%s",
            risk.level.value, outcome.action_taken,
        )

    # ---- 7. 组装响应（结构性无 PII） ----
    # 用户消息回显必须脱敏：与落库使用同一 anonymizer 模块（单一权威实现），
    # 保证"屏幕上看到的"与"数据库里存的"脱敏规则完全一致。
    # 注意：风险评估/情绪识别仍基于原文执行（第 2/4 步），脱敏仅用于回显展示。
    return ChatResponse(
        reply=outcome.reply,
        user_message=anonymize_strict(payload.content),
        emotion=EmotionOut(
            category=emotion.category.value,
            intensity=emotion.intensity,
            confidence=emotion.confidence,
            source=emotion.source,
        ),
        risk=RiskOut(
            level=risk.level,
            label=risk.level.label,
            is_intercepted=outcome.is_intercepted,
            matched_lexicons=risk.matched_lexicons,
        ),
        persona=persona,
        crisis_hotline=services.interceptor.hotline_primary,
        session_state=new_state,
    )
