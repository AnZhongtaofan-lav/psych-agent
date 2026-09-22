# -*- coding: utf-8 -*-
"""
画像构建器 —— 画像推断与逐轮聚合更新（纯函数模块）。

设计说明：
1. 本模块【不直接访问数据库】：输入 Profile 快照与本轮识别结果，
   输出更新后的字段值，持久化由调用方（交互层路由）经仓储层完成
   —— 纯函数设计便于独立测试与复用
2. 聚合算法：
   - dominant_emotions（各类别情绪强度）：指数滑动平均 EMA，
     new = 0.8 × old + 0.2 × current，近期情绪权重更高
   - mood_trend：最近情绪类别列表，截断至 20 条（防无限膨胀）
   - risk_streak：连续高危（L3）轮数——L3 加一、否则归零
   - risk_level_max：历史最高风险等级，只增不减（危机标记保留语义）
3. 画像判定优先级（安全红线）：
   P3（风险 ≥ L2 或历史 max ≥ 2） > P1/P2（信号词计数） > P4（兜底）
"""

from __future__ import annotations

import json

from app.common.constants import (
    MOOD_TREND_WINDOW,
    EmotionCategory,
    PersonaType,
    RiskLevel,
)
from app.core.normalizer import normalize
from app.core.profile.personas import P1_STUDENT, P2_WORKER, PERSONA_REGISTRY

# EMA 平滑系数：旧值权重 0.8（约 10 轮后旧信号衰减到 10%）
_EMA_OLD_WEIGHT = 0.8


def infer_persona(
    normalized_text: str,
    risk_level: RiskLevel,
    historical_risk_max: int,
) -> PersonaType:
    """推断本轮用户画像。

    参数:
        normalized_text: 归一化后的用户输入
        risk_level: 本轮最终风险等级（max 融合后）
        historical_risk_max: 画像中的历史最高风险等级

    返回:
        PersonaType（判定优先级见模块 docstring）
    """
    # 1. P3 强制判定（最高优先级，不可被其他信号覆盖）
    if risk_level >= RiskLevel.L2_HIGH_RISK or historical_risk_max >= 2:
        return PersonaType.P3_CRISIS

    # 2. 信号词计数：学业词 vs 职场词
    student_hits = sum(1 for s in P1_STUDENT.signals if s in normalized_text)
    worker_hits = sum(1 for s in P2_WORKER.signals if s in normalized_text)

    if student_hits > worker_hits and student_hits > 0:
        return PersonaType.P1_STUDENT
    if worker_hits > student_hits and worker_hits > 0:
        return PersonaType.P2_WORKER

    # 3. 兜底：无显著场景信号
    return PersonaType.P4_GENERAL


def update_dominant_emotions(
    current_json: str,
    emotion_category: EmotionCategory,
    emotion_intensity: float,
) -> str:
    """EMA 更新情绪聚合分布，返回新的 JSON 字符串。

    中性/平静情绪也参与聚合（它们同样刻画用户状态），
    但强度为 0 的中性不计入（避免稀释）。
    """
    try:
        current: dict[str, float] = json.loads(current_json) if current_json else {}
    except json.JSONDecodeError:
        # 聚合数据损坏时重置（画像统计是可再生的派生数据，安全）
        current = {}

    updated: dict[str, float] = {}
    all_keys = set(current) | {emotion_category.value}
    for key in all_keys:
        old = current.get(key, 0.0)
        if key == emotion_category.value and emotion_intensity > 0:
            new_value = _EMA_OLD_WEIGHT * old + (1 - _EMA_OLD_WEIGHT) * emotion_intensity
        else:
            # 本轮未出现的类别：只做衰减，保持分布归一性
            new_value = old * _EMA_OLD_WEIGHT
        # 清洗：衰减到阈值以下的键直接移除，防止 JSON 无限膨胀
        if new_value >= 0.01:
            updated[key] = round(new_value, 4)
    return json.dumps(updated, ensure_ascii=False)


def update_mood_trend(current_json: str, emotion_category: EmotionCategory) -> str:
    """追加本轮情绪到滚动窗口（截断至 20 条），返回新的 JSON 字符串。"""
    try:
        trend: list[str] = json.loads(current_json) if current_json else []
    except json.JSONDecodeError:
        trend = []
    trend.append(emotion_category.value)
    # 截断：只保留最近 N 条（负切片：保留尾部）
    trend = trend[-MOOD_TREND_WINDOW:]
    return json.dumps(trend, ensure_ascii=False)


def next_risk_streak(current_streak: int, risk_level: RiskLevel) -> int:
    """计算新的连续高危轮数：L3 加一，否则归零。"""
    return current_streak + 1 if risk_level >= RiskLevel.L3_CRISIS else 0


def build_profile_update(
    *,
    profile_json_emotions: str,
    profile_json_trend: str,
    current_risk_max: int,
    current_streak: int,
    emotion_category: EmotionCategory,
    emotion_intensity: float,
    risk_level: RiskLevel,
    persona: PersonaType,
) -> dict:
    """一轮对话后的画像字段批量计算（供路由层一次性持久化）。

    返回字典字段：
        dominant_emotions / mood_trend: JSON 字符串
        risk_level_max / risk_streak: 整数
        persona_type: 画像枚举值字符串
    """
    return {
        "dominant_emotions": update_dominant_emotions(
            profile_json_emotions, emotion_category, emotion_intensity
        ),
        "mood_trend": update_mood_trend(profile_json_trend, emotion_category),
        "risk_level_max": max(current_risk_max, risk_level.value),
        "risk_streak": next_risk_streak(current_streak, risk_level),
        "persona_type": persona.value,
    }


def extract_signals(normalized_text: str, persona: PersonaType) -> list[str]:
    """提取文本命中的画像信号词（供回复生成器做场景化回应）。"""
    definition = PERSONA_REGISTRY.get(persona)
    if definition is None or not definition.signals:
        return []
    return [s for s in definition.signals if s in normalized_text]


__all__ = [
    "build_profile_update",
    "extract_signals",
    "infer_persona",
    "next_risk_streak",
    "normalize",
    "update_dominant_emotions",
    "update_mood_trend",
]
