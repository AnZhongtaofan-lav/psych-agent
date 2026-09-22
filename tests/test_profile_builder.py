# -*- coding: utf-8 -*-
"""
画像构建器测试（对应设计方案测试计划 D1~D4）。

覆盖目标：
1. 画像推断：信号词 → P1/P2；风险 → 强制 P3（含历史标记）
2. 聚合更新：EMA 情绪分布、mood_trend 截断、streak 归零但 max 保留
3. 交互计数递增
"""

from __future__ import annotations

import json

from app.common.constants import EmotionCategory, PersonaType, RiskLevel
from app.core.profile.profile_builder import (
    build_profile_update,
    infer_persona,
    next_risk_streak,
    update_dominant_emotions,
    update_mood_trend,
)


class TestPersonaInference:
    """画像判定优先级。"""

    def test_student_signals(self):
        """学业词占优 → P1。"""
        persona = infer_persona("明天要考试了，怕挂科", RiskLevel.L0_NORMAL, 0)
        assert persona == PersonaType.P1_STUDENT

    def test_worker_signals(self):
        """职场词占优 → P2。"""
        persona = infer_persona("老板又让我加班到凌晨", RiskLevel.L0_NORMAL, 0)
        assert persona == PersonaType.P2_WORKER

    def test_no_signals_fallback_p4(self):
        """无信号词 → P4 兜底。"""
        persona = infer_persona("今天有点心神不宁", RiskLevel.L0_NORMAL, 0)
        assert persona == PersonaType.P4_GENERAL

    def test_l2_forces_p3(self):
        """本轮 L2 → 强制 P3（覆盖信号词判定）。"""
        persona = infer_persona("老板让我加班", RiskLevel.L2_HIGH_RISK, 0)
        assert persona == PersonaType.P3_CRISIS

    def test_historical_risk_forces_p3(self):
        """历史 risk_level_max ≥ 2 → 即使本轮 L0 也强制 P3（危机标记保留）。"""
        persona = infer_persona("今天挺好的", RiskLevel.L0_NORMAL, historical_risk_max=3)
        assert persona == PersonaType.P3_CRISIS


class TestAggregation:
    """逐轮聚合更新。"""

    def test_d1_ema_rises_with_repeats(self):
        """D1: 连续多轮焦虑 → dominant_emotions 焦虑值持续上升。"""
        emotions = "{}"
        values = []
        for _ in range(5):
            emotions = update_dominant_emotions(
                emotions, EmotionCategory.ANXIETY, 0.8
            )
            values.append(json.loads(emotions)["焦虑"])
        assert values == sorted(values)  # 单调不减
        assert values[-1] > 0.5

    def test_dominant_emotion_key(self):
        """连续焦虑后，焦虑应为分布中最高键。"""
        emotions = "{}"
        for _ in range(3):
            emotions = update_dominant_emotions(
                emotions, EmotionCategory.ANXIETY, 0.8
            )
        dist = json.loads(emotions)
        assert max(dist, key=dist.get) == "焦虑"  # type: ignore[arg-type]

    def test_d2_l3_updates(self):
        """D2: 一轮 L3 → risk_level_max=3、persona=P3、streak=1。"""
        update = build_profile_update(
            profile_json_emotions="{}",
            profile_json_trend="[]",
            current_risk_max=0,
            current_streak=0,
            emotion_category=EmotionCategory.DEPRESSION,
            emotion_intensity=0.9,
            risk_level=RiskLevel.L3_CRISIS,
            persona=PersonaType.P3_CRISIS,
        )
        assert update["risk_level_max"] == 3
        assert update["risk_streak"] == 1
        assert update["persona_type"] == "P3"

    def test_d3_streak_resets_but_max_kept(self):
        """D3: 高危后正常轮 → streak 归零，risk_level_max 保留。"""
        update = build_profile_update(
            profile_json_emotions="{}",
            profile_json_trend="[]",
            current_risk_max=3,
            current_streak=2,
            emotion_category=EmotionCategory.CALM,
            emotion_intensity=0.3,
            risk_level=RiskLevel.L0_NORMAL,
            persona=PersonaType.P3_CRISIS,  # 历史危机标记仍在
        )
        assert update["risk_streak"] == 0
        assert update["risk_level_max"] == 3  # 只增不减

    def test_d4_mood_trend_truncated(self):
        """D4: mood_trend 截断至 20 条；interaction_count 由调用方累加。"""
        trend = "[]"
        for _ in range(25):
            trend = update_mood_trend(trend, EmotionCategory.ANXIETY)
        assert len(json.loads(trend)) == 20

    def test_streak_semantics(self):
        """streak：L3 加一、非 L3 归零。"""
        assert next_risk_streak(2, RiskLevel.L3_CRISIS) == 3
        assert next_risk_streak(2, RiskLevel.L1_ATTENTION) == 0
        assert next_risk_streak(0, RiskLevel.L2_HIGH_RISK) == 0
