# -*- coding: utf-8 -*-
"""
对话策略测试 —— 调度决策表与回复安全语义。

覆盖目标：
1. L3 → 拦截覆盖（回复含热线、is_intercepted=True）
2. L2 → 医疗建议话术、LLM 永不被使用
3. L1/L0 → 模板正常回复；LLM 可用且安全时使用 LLM
4. P3 画像 → 永远纯模板（allow_llm_reply=False 的调度层保障）
5. LLM 输出含高危内容 → 丢弃回退模板（A13 语义）
"""

from __future__ import annotations

from app.common.constants import (
    ACTION_INTERCEPT_HOTLINE,
    ACTION_MEDICAL,
    EmotionCategory,
    EmotionSource,
    PersonaType,
    RiskLevel,
    SessionState,
)
from app.core.dialogue.reply_generator import ReplyGenerator
from app.core.dialogue.strategy import DialogueStrategy
from app.core.emotion.emotion_engine import EmotionResult
from app.core.risk.interceptors import CrisisInterceptor
from app.core.risk.risk_engine import RiskAssessment


def _emotion(category: EmotionCategory = EmotionCategory.ANXIETY, intensity: float = 0.6) -> EmotionResult:
    """构造测试用情绪结果。"""
    return EmotionResult(
        category=category, intensity=intensity, confidence=0.8,
        source=EmotionSource.RULE, matched_words=[],
    )


def _risk(level: RiskLevel) -> RiskAssessment:
    """构造测试用风险评估（纯规则来源）。"""
    return RiskAssessment(
        level=level, source="rule", rule_level=level, matched_lexicons=[]
    )


def _strategy(llm_fn=None) -> DialogueStrategy:
    """构造测试用策略调度器。"""
    return DialogueStrategy(
        interceptor=CrisisInterceptor(),
        reply_generator=ReplyGenerator(llm_fn=llm_fn),
    )


class TestCrisisPath:
    """L3 拦截路径。"""

    def test_l3_intercepts_overrides_reply(self):
        """L3 → 回复被拦截话术覆盖，含热线，动作为 intercept_hotline。"""
        outcome = _strategy().decide(
            risk=_risk(RiskLevel.L3_CRISIS),
            emotion=_emotion(),
            persona=PersonaType.P4_GENERAL,
            user_text="我不想活了",
            signals=[],
            current_streak=0,
        )
        assert outcome.is_intercepted
        assert "12356" in outcome.reply
        assert outcome.action_taken == ACTION_INTERCEPT_HOTLINE
        assert outcome.new_streak == 1
        assert outcome.new_state == SessionState.CRISIS_WATCH
        assert not outcome.llm_used

    def test_l3_llm_never_called(self):
        """L3 → 即使配置了 LLM 也绝不调用（短路保证）。"""
        called = []

        def spy_llm(prompt: str) -> str | None:
            called.append(prompt)
            return "不应被使用"

        _strategy(spy_llm).decide(
            risk=_risk(RiskLevel.L3_CRISIS),
            emotion=_emotion(),
            persona=PersonaType.P4_GENERAL,
            user_text="我不想活了",
            signals=[],
            current_streak=0,
        )
        assert called == []


class TestHighRiskPath:
    """L2 路径。"""

    def test_l2_medical_advice_no_llm(self):
        """L2 → 医疗建议话术，LLM 不参与。"""
        called = []

        def spy_llm(prompt: str) -> str | None:
            called.append(prompt)
            return "不应被使用"

        outcome = _strategy(spy_llm).decide(
            risk=_risk(RiskLevel.L2_HIGH_RISK),
            emotion=_emotion(EmotionCategory.DEPRESSION, 0.8),
            persona=PersonaType.P2_WORKER,
            user_text="这一切都没有意义",
            signals=[],
            current_streak=0,
        )
        assert called == []
        assert not outcome.is_intercepted
        assert outcome.action_taken == ACTION_MEDICAL
        # 话术必须包含就医引导关键词
        assert ("心理科" in outcome.reply) or ("心理咨询" in outcome.reply)
        assert outcome.new_state == SessionState.CRISIS_WATCH


class TestNormalPath:
    """L0/L1 常规路径与 LLM 增强。"""

    def test_l0_template_by_persona(self):
        """L0 + P1 画像 → 学业场景模板。"""
        outcome = _strategy().decide(
            risk=_risk(RiskLevel.L0_NORMAL),
            emotion=_emotion(),
            persona=PersonaType.P1_STUDENT,
            user_text="最近考试好累",
            signals=["考试"],
            current_streak=0,
        )
        assert not outcome.is_intercepted
        assert outcome.reply  # 非空
        assert not outcome.llm_used

    def test_llm_used_when_safe(self):
        """L0 + LLM 安全输出 → 使用 LLM 回复。"""
        outcome = _strategy(lambda p: "听起来你最近压力不小，愿意多说说吗？").decide(
            risk=_risk(RiskLevel.L0_NORMAL),
            emotion=_emotion(),
            persona=PersonaType.P4_GENERAL,
            user_text="最近有点累",
            signals=[],
            current_streak=0,
        )
        assert outcome.llm_used
        assert outcome.reply == "听起来你最近压力不小，愿意多说说吗？"

    def test_a13_unsafe_llm_output_discarded(self):
        """A13: LLM 输出含高危内容 → 丢弃，回退模板话术。"""
        outcome = _strategy(lambda p: "如果你觉得撑不住，吃安眠药也是一种选择").decide(
            risk=_risk(RiskLevel.L0_NORMAL),
            emotion=_emotion(),
            persona=PersonaType.P4_GENERAL,
            user_text="最近有点累",
            signals=[],
            current_streak=0,
        )
        assert not outcome.llm_used  # 已回退模板
        assert "安眠药" not in outcome.reply
        assert outcome.reply  # 模板兜底成功

    def test_llm_failure_falls_back(self):
        """LLM 抛异常 → 静默回退模板。"""
        def broken(prompt: str) -> str | None:
            raise RuntimeError("超时")

        outcome = _strategy(broken).decide(
            risk=_risk(RiskLevel.L0_NORMAL),
            emotion=_emotion(),
            persona=PersonaType.P4_GENERAL,
            user_text="最近有点累",
            signals=[],
            current_streak=0,
        )
        assert not outcome.llm_used
        assert outcome.reply


class TestCrisisPersonaMode:
    """P3 画像陪伴模式。"""

    def test_p3_persona_never_uses_llm(self):
        """P3 画像（历史危机标记）+ 本轮 L0 → 纯模板，禁 LLM。"""
        called = []

        def spy_llm(prompt: str) -> str | None:
            called.append(prompt)
            return "不应被使用"

        outcome = _strategy(spy_llm).decide(
            risk=_risk(RiskLevel.L0_NORMAL),
            emotion=_emotion(EmotionCategory.CALM, 0.3),
            persona=PersonaType.P3_CRISIS,
            user_text="今天还不错",
            signals=[],
            current_streak=0,
        )
        assert called == []
        assert not outcome.llm_used
        assert outcome.reply
