# -*- coding: utf-8 -*-
"""
情绪识别引擎测试（对应设计方案测试计划 C1~C6）。

覆盖目标：
1. 基础分类：焦虑/愤怒/平静（C1~C3）
2. 混合情绪取最强（C4）
3. 无情绪词 → 中性 + 低置信度（C5）
4. LLM 融合：置信度高者胜出、异常降级、未知类别丢弃（C6 + 补充）
"""

from __future__ import annotations

from app.common.constants import EmotionCategory, EmotionSource
from app.core.emotion.emotion_engine import EmotionEngine, LlmEmotion
from app.core.emotion.rules import EmotionRules


class TestRuleClassification:
    """规则分类器核心用例。"""

    def test_c1_anxiety(self):
        """C1: "我明天要考试了好紧张" → 焦虑，强度>0.5（"好"字放大 0.6×1.25）。"""
        result = EmotionRules().classify("我明天要考试了好紧张")
        assert result.category == EmotionCategory.ANXIETY
        assert result.intensity > 0.5

    def test_c2_anger(self):
        """C2: "气死我了老板又让我加班" → 愤怒。"""
        result = EmotionRules().classify("气死我了老板又让我加班")
        assert result.category == EmotionCategory.ANGER

    def test_c3_calm(self):
        """C3: "今天挺平静的" → 平静，低唤醒强度<0.3。"""
        result = EmotionRules().classify("今天挺平静的")
        assert result.category == EmotionCategory.CALM
        assert result.intensity < 0.3

    def test_c4_mixed_emotion(self):
        """C4: "又焦虑又难过" → 主类别取强度最高者（焦虑 0.8 > 难过 0.7）。"""
        result = EmotionRules().classify("又焦虑又难过")
        assert result.category == EmotionCategory.ANXIETY

    def test_c5_no_emotion_words(self):
        """C5: 无情绪词输入 → 中性 + 低置信度。"""
        result = EmotionRules().classify("帮我确认一下现在几点了")
        assert result.category == EmotionCategory.NEUTRAL
        assert result.intensity == 0.0
        assert result.confidence <= 0.4

    def test_intensifier_amplifies(self):
        """程度副词放大："非常害怕" > "害怕" 的基础强度。"""
        base = EmotionRules().classify("害怕")
        amplified = EmotionRules().classify("非常害怕")
        assert amplified.intensity > base.intensity


class TestFusionWithLlm:
    """规则 × LLM 融合语义。"""

    def test_c6_llm_wins_with_higher_confidence(self):
        """C6: LLM 置信度更高 → 以 LLM 为主结果，source=rule+llm。"""
        engine = EmotionEngine(
            llm_emotion_fn=lambda t: LlmEmotion(
                category="悲伤", intensity=0.8, confidence=0.9
            )
        )
        result = engine.analyze("我明天要考试了好紧张")
        assert result.category == EmotionCategory.SADNESS
        assert result.source == EmotionSource.RULE_LLM
        assert result.confidence == 0.9

    def test_rule_wins_when_llm_confidence_lower(self):
        """规则置信度更高 → 保持规则结果（但 source 记 rule+llm）。"""
        engine = EmotionEngine(
            llm_emotion_fn=lambda t: LlmEmotion(
                category="焦虑", intensity=0.5, confidence=0.4
            )
        )
        result = engine.analyze("我明天要考试了好紧张")
        assert result.category == EmotionCategory.ANXIETY
        assert result.source == EmotionSource.RULE_LLM

    def test_llm_unknown_category_discarded(self):
        """LLM 返回未知类别 → 视为无效贡献，回退纯规则。"""
        engine = EmotionEngine(
            llm_emotion_fn=lambda t: LlmEmotion(
                category="狂喜", intensity=0.9, confidence=0.99
            )
        )
        result = engine.analyze("我明天要考试了好紧张")
        assert result.category == EmotionCategory.ANXIETY
        assert result.source == EmotionSource.RULE

    def test_llm_exception_degrades(self):
        """LLM 抛异常 → 静默回退纯规则结果。"""
        def broken(t: str) -> LlmEmotion:
            raise RuntimeError("网络超时")

        result = EmotionEngine(llm_emotion_fn=broken).analyze("气死我了")
        assert result.category == EmotionCategory.ANGER
        assert result.source == EmotionSource.RULE

    def test_pure_rule_mode(self):
        """未配置 LLM → source=rule 的纯规则结果。"""
        result = EmotionEngine().analyze("今天挺平静的")
        assert result.source == EmotionSource.RULE
        assert result.category == EmotionCategory.CALM
