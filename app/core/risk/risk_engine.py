# -*- coding: utf-8 -*-
"""
风险分级引擎 —— 规则与可选 LLM 评级的 max 融合决策点。

核心语义（安全红线，测试覆盖）：
    final_level = max(rule_level, llm_level)
    - LLM 只能把风险往【高】调，永远不能往【低】调
      （LLM 可能被诱导输出"L0 无风险"，规则引擎是唯一可信兜底）
    - 规则命中 L3 时【短路跳过 LLM 调用】：
      a) 高危拦截要求低延迟（危机场景每秒都重要）
      b) 拦截必须确定性发生，不依赖任何外部服务的可用性
    - LLM 评估抛出任何异常 → 静默降级为纯规则结果
      （不向用户暴露内部错误，不让 LLM 故障拖垮安全链路）

误报优于漏报：
    规则无法区分"用户自述"与"转述他人"（如"我朋友说不想活了"），
    一律按用户自述处理 —— 这是心理安全领域的公认取舍。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.common.constants import RiskLevel
from app.common.logger import get_logger
from app.core.normalizer import normalize
from app.core.risk.risk_rules import RiskRules

logger = get_logger(__name__)

# LLM 评级函数签名：输入原始文本，返回 RiskLevel 或 None（无法评估）
LlmLevelFn = Callable[[str], "RiskLevel | None"]


@dataclass
class RiskAssessment:
    """风险评估结果。

    属性:
        level: 最终风险等级（max 融合后）
        source: 判定来源 rule / llm / rule+llm（审计与调试用）
        rule_level: 规则引擎独立判定结果
        llm_level: LLM 独立判定结果（None = 未调用或不可用）
        matched_lexicons: 命中的词典条目标签（词典标签，非用户原文）
    """

    level: RiskLevel
    source: str
    rule_level: RiskLevel
    llm_level: RiskLevel | None = None
    matched_lexicons: list[str] = field(default_factory=list)

    @property
    def is_crisis(self) -> bool:
        """是否危机级（L3）—— 拦截器据此接管回复。"""
        return self.level >= RiskLevel.L3_CRISIS


class RiskEngine:
    """风险分级引擎。

    参数:
        llm_level_fn: 可选的 LLM 风险评级函数（由 LLM 客户端注入）。
            None 表示纯规则模式（未配置 LLM / 显式禁用）。
    """

    def __init__(self, llm_level_fn: LlmLevelFn | None = None) -> None:
        self._rules = RiskRules()
        self._llm_level_fn = llm_level_fn

    def assess(self, raw_text: str) -> RiskAssessment:
        """对一条用户输入执行完整风险评估。

        流水线:
            原文 → 归一化 → 规则匹配(最高级)
                 → [规则 < L3 且 LLM 可用] LLM 评级
                 → max 融合 → RiskAssessment
        """
        # 1. 归一化（全角/小写/谐音映射/去插空）—— 反绕过第一道工序
        normalized = normalize(raw_text)

        # 2. 规则匹配（确定性兜底）
        rule_result = self._rules.match(normalized)
        rule_level = RiskLevel(rule_result.level)

        # 3. 短路：规则已判 L3 → 直接返回，绝不调用 LLM
        #    （拦截的确定性与低延迟都由这一行保证）
        if rule_level >= RiskLevel.L3_CRISIS or self._llm_level_fn is None:
            return RiskAssessment(
                level=rule_level,
                source="rule",
                rule_level=rule_level,
                llm_level=None,
                matched_lexicons=rule_result.entries,
            )

        # 4. LLM 评级（可选增强）：任何异常都静默降级
        llm_level: RiskLevel | None = None
        try:
            llm_level = self._llm_level_fn(raw_text)
        except Exception:  # noqa: BLE001 —— LLM 故障绝不能影响安全链路
            logger.warning("LLM 风险评级失败，降级为纯规则结果")

        # 5. max 融合：LLM 只能升级不能降级
        if llm_level is None:
            return RiskAssessment(
                level=rule_level, source="rule", rule_level=rule_level,
                matched_lexicons=rule_result.entries,
            )

        final = max(rule_level, llm_level)
        return RiskAssessment(
            level=final,
            source="rule+llm" if llm_level != rule_level else "rule",
            rule_level=rule_level,
            llm_level=llm_level,
            matched_lexicons=rule_result.entries,
        )
