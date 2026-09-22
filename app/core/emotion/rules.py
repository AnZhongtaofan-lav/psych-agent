# -*- coding: utf-8 -*-
"""
规则情绪分类器 —— 词典驱动的离线情绪识别。

设计说明：
1. 数据源：resources/emotion_lexicon.json
   - words: 情绪词 → 基础强度（0~1）
   - intensifiers: 程度副词 → 放大系数（"非常紧张" > "紧张"）
2. 强度合成：词命中强度 = min(1.0, 基础强度 × 前置程度副词系数)
   类别得分 = 该类别所有命中词的最高强度（max 语义：一个"恐惧"就是强信号）
3. 主类别 = 得分最高的类别；并列时按词典定义顺序（保证确定性）
4. 置信度随命中词数量增长（多词佐证 → 更可信），封顶 0.95
5. 匹配输入为归一化文本（与风险匹配同一管线，保证 "emo"/大小写等形态统一）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.common.constants import EmotionCategory
from app.common.logger import get_logger

logger = get_logger(__name__)

# 词典路径：app/core/emotion/rules.py → 上两级 → app/resources/
_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent / "resources" / "emotion_lexicon.json"

# 程度副词回溯窗口：只看情绪词前面最多 3 个字符
_INTENSIFIER_WINDOW = 3


@dataclass
class RuleEmotionResult:
    """规则情绪分类结果。

    属性:
        category: 主情绪类别
        intensity: 主类别强度 0~1（无命中为 0）
        confidence: 置信度 0~1
        matched_words: 命中的情绪词（供审计与回复生成参考）
        scores: 各类别得分快照（供画像聚合使用）
    """

    category: EmotionCategory
    intensity: float
    confidence: float
    matched_words: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


@lru_cache(maxsize=1)
def _load_lexicon() -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """加载情绪词典（lru_cache 全局单次加载）。

    返回:
        (categories: 类别 → {词: 基础强度}, intensifiers: 副词 → 系数)

    安全语义：词典缺失时 fail-fast 抛异常（情绪识别是核心能力，
    静默失败会让所有输入变成"中性"，画像与策略全部失真）。
    """
    raw = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    intensifiers = dict(raw["intensifiers"])
    categories = {
        cat: {word: float(base) for word, base in words["words"].items()}
        for cat, words in raw["categories"].items()
        if not cat.startswith("_")  # 跳过 _note 等注释键
    }
    logger.info(
        "情绪词典加载完成: %d 类, %d 个程度副词",
        len(categories), len(intensifiers),
    )
    return categories, intensifiers


def _find_intensifier_before(text: str, start: int) -> float:
    """在情绪词之前的窗口内查找程度副词（长词优先，避免"超"误配"超级"）。

    参数:
        text: 归一化文本
        start: 情绪词起始下标

    返回:
        放大系数（无副词命中时为 1.0）
    """
    categories, intensifiers = _load_lexicon()
    window_start = max(0, start - _INTENSIFIER_WINDOW)
    window = text[window_start:start]
    # 长副词优先匹配（如 "超级" 先于 "超"）
    for adv in sorted(intensifiers, key=len, reverse=True):
        if adv and window.endswith(adv):
            return intensifiers[adv]
    return 1.0


class EmotionRules:
    """规则情绪分类器。"""

    def __init__(self) -> None:
        # 构造期触发加载（fail-fast 提前到启动阶段）
        self._categories, self._intensifiers = _load_lexicon()

    def classify(self, normalized_text: str) -> RuleEmotionResult:
        """在归一化文本上执行词典情绪分类。

        参数:
            normalized_text: normalizer.normalize() 的输出

        返回:
            RuleEmotionResult；无任何命中时 category=中性、intensity=0、低置信度
        """
        scores: dict[str, float] = {cat: 0.0 for cat in self._categories}
        matched: list[str] = []

        for cat, words in self._categories.items():
            for word, base in words.items():
                # 找出该词在文本中的全部出现位置
                for match in re.finditer(re.escape(word), normalized_text):
                    factor = _find_intensifier_before(normalized_text, match.start())
                    effective = min(1.0, base * factor)
                    if effective > scores[cat]:
                        scores[cat] = effective
                    if word not in matched:
                        matched.append(word)

        # 主类别：得分最高者。
        # 并列时 max 保留迭代序中第一个 —— dict 保序（JSON 定义顺序），结果确定
        dominant = max(scores, key=scores.get)  # type: ignore[arg-type]
        intensity = scores[dominant]

        if not matched:
            # 无命中：中性 + 低置信度（诚实表达"我不确定"）
            return RuleEmotionResult(
                category=EmotionCategory.NEUTRAL,
                intensity=0.0,
                confidence=0.3,
                matched_words=[],
                scores=scores,
            )

        # 置信度：随独立命中词数量增长（0.6 → 0.85 封顶）
        confidence = min(0.85, 0.6 + 0.12 * (len(matched) - 1))
        return RuleEmotionResult(
            category=EmotionCategory(dominant),
            intensity=round(intensity, 3),
            confidence=round(confidence, 3),
            matched_words=matched,
            scores=scores,
        )
