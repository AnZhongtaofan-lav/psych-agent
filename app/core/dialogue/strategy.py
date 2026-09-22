# -*- coding: utf-8 -*-
"""
对话策略调度中枢 —— 按 (风险等级 × 用户画像) 决定本轮回复路径。

决策表（安全优先，从上到下短路）：
    ┌────────┬──────────────────────────────────────────────┐
    │ L3 危机 │ 拦截器接管：覆盖回复 + 热线转介 + streak 升级    │
    │ L2 高风险│ 关怀 + 建议就医（陪伴模式，仅模板，禁 LLM）      │
    │ L1 关注 │ 引导倾诉模板；LLM 增强可选（画像允许时）          │
    │ L0 正常 │ 画像策略模板；LLM 增强可选（画像允许时）          │
    └────────┴──────────────────────────────────────────────┘
    另：P3 画像（历史危机标记）即使本轮 L0/L1 也走陪伴式模板（禁 LLM）。

本模块为纯调度（无 IO）：输入各引擎结果与会话快照，输出 ChatOutcome，
持久化由路由层完成。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.common.constants import (
    ACTION_GUIDE,
    ACTION_INTERCEPT_HOTLINE,
    ACTION_MEDICAL,
    ACTION_NORMAL,
    PersonaType,
    RiskLevel,
    SessionState,
)
from app.core.dialogue.reply_generator import ReplyGenerator
from app.core.emotion.emotion_engine import EmotionResult
from app.core.profile.personas import PERSONA_REGISTRY
from app.core.risk.interceptors import CrisisInterceptor
from app.core.risk.risk_engine import RiskAssessment


@dataclass
class ChatOutcome:
    """一轮对话的最终产出（路由层据此组装响应与持久化）。

    属性:
        reply: 最终回复文本
        is_intercepted: 是否被 L3 拦截（覆盖回复）
        action_taken: 风险响应动作（normal/guide/medical/intercept_hotline）
        new_streak: 更新后的连续高危轮数
        new_state: 会话应进入的新状态（None = 不变更）
        persona: 本轮判定的画像
        llm_used: 回复是否由 LLM 生成（审计用）
    """

    reply: str
    is_intercepted: bool
    action_taken: str
    new_streak: int
    new_state: SessionState | None
    persona: PersonaType
    llm_used: bool


class DialogueStrategy:
    """对话策略调度器。"""

    def __init__(
        self,
        interceptor: CrisisInterceptor,
        reply_generator: ReplyGenerator,
    ) -> None:
        self._interceptor = interceptor
        self._replies = reply_generator

    def decide(
        self,
        *,
        risk: RiskAssessment,
        emotion: EmotionResult,
        persona: PersonaType,
        user_text: str,
        signals: list[str],
        current_streak: int,
    ) -> ChatOutcome:
        """执行一轮对话决策。

        参数:
            risk: 风险评估结果（max 融合后）
            emotion: 情绪识别结果
            persona: 本轮画像（由 profile_builder.infer_persona 判定）
            user_text: 用户原始输入（仅 LLM 提示词使用，不会落日志）
            signals: 命中的画像信号词
            current_streak: 会话当前连续高危轮数
        """
        # ---- L3 危机：拦截器接管（最高优先级，短路一切） ----
        if risk.is_crisis:
            outcome = self._interceptor.intercept(current_streak)
            return ChatOutcome(
                reply=outcome.reply,
                is_intercepted=True,
                action_taken=ACTION_INTERCEPT_HOTLINE,
                new_streak=outcome.new_streak,
                new_state=outcome.new_state,
                persona=persona,
                llm_used=False,
            )

        # ---- P3 画像陪伴模式：历史危机用户走纯模板（禁 LLM） ----
        if persona == PersonaType.P3_CRISIS:
            return ChatOutcome(
                reply=self._replies.generate_template_reply(risk, persona, emotion, signals),
                is_intercepted=False,
                action_taken=ACTION_GUIDE if risk.level == 1 else ACTION_NORMAL,
                new_streak=0,
                new_state=None,
                persona=persona,
                llm_used=False,
            )

        # ---- L2 高风险：关怀 + 建议就医（仅模板，进入陪伴模式） ----
        if risk.level >= RiskLevel.L2_HIGH_RISK:
            return ChatOutcome(
                reply=self._replies.generate_template_reply(risk, persona, emotion, signals),
                is_intercepted=False,
                action_taken=ACTION_MEDICAL,
                new_streak=0,
                new_state=SessionState.CRISIS_WATCH,  # 标记会话高风险看护
                persona=persona,
                llm_used=False,
            )

        # ---- L1/L0：模板优先，LLM 增强可选 ----
        llm_reply = self._replies.generate_llm_reply(user_text, risk, persona, emotion)
        if llm_reply is not None:
            return ChatOutcome(
                reply=llm_reply,
                is_intercepted=False,
                action_taken=ACTION_GUIDE if risk.level == 1 else ACTION_NORMAL,
                new_streak=0,
                new_state=None,
                persona=persona,
                llm_used=True,
            )
        return ChatOutcome(
            reply=self._replies.generate_template_reply(risk, persona, emotion, signals),
            is_intercepted=False,
            action_taken=ACTION_GUIDE if risk.level == 1 else ACTION_NORMAL,
            new_streak=0,
            new_state=None,
            persona=persona,
            llm_used=False,
        )


__all__ = ["ChatOutcome", "DialogueStrategy", "PERSONA_REGISTRY"]
