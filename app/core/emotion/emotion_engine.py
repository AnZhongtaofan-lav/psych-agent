# -*- coding: utf-8 -*-
"""
情绪识别引擎 —— 规则 + 可选 LLM 融合。

融合策略（与风险引擎的 max 语义不同，注意区分）：
    - 风险：max(rule, llm) —— 安全优先，只升不降
    - 情绪：【置信度高者胜出】—— 情绪没有"安全底线"语义，
      谁更可信听谁的；LLM 置信度更高时以 LLM 为主结果
    - LLM 返回未知类别 / None / 抛异常 → 一律回退纯规则（fail-safe）
    - source 规则：
        rule      仅规则（未配置 LLM、LLM 失败、LLM 无贡献）
        rule+llm  LLM 参与了最终结果（无论其是否胜出）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.common.constants import EmotionCategory, EmotionSource
from app.common.logger import get_logger
from app.core.emotion.rules import EmotionRules, RuleEmotionResult
from app.core.normalizer import normalize

logger = get_logger(__name__)


@dataclass(frozen=True)
class LlmEmotion:
    """LLM 情绪分类输出（由 LLM 客户端解析 JSON 后构造）。

    属性:
        category: 类别名（必须能映射到 EmotionCategory，否则被丢弃）
        intensity: 强度 0~1
        confidence: 置信度 0~1
    """

    category: str
    intensity: float
    confidence: float


# LLM 情绪函数签名：输入原始文本 → 可选 LlmEmotion
LlmEmotionFn = Callable[[str], "LlmEmotion | None"]


@dataclass
class EmotionResult:
    """情绪识别最终结果（对外统一出口，写入 messages 表的标注字段）。

    属性:
        category: 主情绪类别
        intensity: 强度 0~1
        confidence: 置信度 0~1
        source: rule / llm / rule+llm
        matched_words: 规则命中的情绪词（LLM 路径为空）
    """

    category: EmotionCategory
    intensity: float
    confidence: float
    source: EmotionSource
    matched_words: list[str]


class EmotionEngine:
    """情绪识别引擎。

    参数:
        llm_emotion_fn: 可选的 LLM 情绪分类函数；None = 纯规则模式
    """

    def __init__(self, llm_emotion_fn: LlmEmotionFn | None = None) -> None:
        self._rules = EmotionRules()
        self._llm_emotion_fn = llm_emotion_fn

    def analyze(self, raw_text: str) -> EmotionResult:
        """对一条用户输入执行情绪识别（规则 → 可选 LLM → 融合）。"""
        normalized = normalize(raw_text)
        rule_res = self._rules.classify(normalized)

        # 纯规则模式：LLM 未配置 → 直接返回
        if self._llm_emotion_fn is None:
            return self._from_rule(rule_res, EmotionSource.RULE)

        # LLM 增强：任何失败都静默回退规则结果
        try:
            llm_res = self._llm_emotion_fn(raw_text)
        except Exception:  # noqa: BLE001 —— LLM 故障不影响主流程
            logger.warning("LLM 情绪分类失败，回退纯规则结果")
            return self._from_rule(rule_res, EmotionSource.RULE)

        if llm_res is None:
            return self._from_rule(rule_res, EmotionSource.RULE)

        # LLM 类别必须是受控枚举值，否则视为无效贡献
        try:
            llm_category = EmotionCategory(llm_res.category)
        except ValueError:
            logger.warning("LLM 返回未知情绪类别，已忽略: %s", llm_res.category)
            return self._from_rule(rule_res, EmotionSource.RULE)

        # 融合：置信度高者胜出（情绪无安全底线语义，可信度优先）
        if llm_res.confidence > rule_res.confidence:
            return EmotionResult(
                category=llm_category,
                intensity=min(1.0, max(0.0, llm_res.intensity)),
                confidence=min(1.0, max(0.0, llm_res.confidence)),
                source=EmotionSource.RULE_LLM,
                matched_words=rule_res.matched_words,
            )
        return EmotionResult(
            category=rule_res.category,
            intensity=rule_res.intensity,
            confidence=rule_res.confidence,
            source=EmotionSource.RULE_LLM,  # LLM 参与了比较 → 记 rule+llm
            matched_words=rule_res.matched_words,
        )

    @staticmethod
    def _from_rule(rule_res: RuleEmotionResult, source: EmotionSource) -> EmotionResult:
        """规则结果 → 统一出口的转换。"""
        return EmotionResult(
            category=rule_res.category,
            intensity=rule_res.intensity,
            confidence=rule_res.confidence,
            source=source,
            matched_words=rule_res.matched_words,
        )
