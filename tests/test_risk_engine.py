# -*- coding: utf-8 -*-
"""
风险分级引擎测试（对应设计方案测试计划 A1~A10、A12 + LLM 融合语义）。

覆盖目标：
1. 直白高危表述（A1/A6/A7）
2. 变体绕过：拼音混合/谐音数字/首字母/插空/全角标点（A2~A5）
3. 分级边界：L1 不拦截、L2 建议就医、L0 正常（A8~A10）
4. max 融合语义：LLM 只能升级不能降级（A12 及相关用例）
5. LLM 故障静默降级（可用性红线）
"""

from __future__ import annotations

from app.common.constants import RiskLevel
from app.core.risk.risk_engine import RiskEngine


def _engine(llm=None) -> RiskEngine:
    """构造纯规则引擎（LLM 未配置场景 = 生产默认）。"""
    return RiskEngine(llm_level_fn=llm)


class TestCrisisDetection:
    """L3 危机级判定（含变体绕过）。"""

    def test_a1_direct_statement(self):
        """A1: 直白自杀意念 → L3。"""
        result = _engine().assess("我不想活了")
        assert result.level == RiskLevel.L3_CRISIS
        assert result.source == "rule"
        assert result.matched_lexicons  # 必须记录命中条目供审计

    def test_a2_pinyin_mixed(self):
        """A2: 拼音混合"我不想huo了" → 归一化映射后 L3。"""
        result = _engine().assess("我不想huo了")
        assert result.level == RiskLevel.L3_CRISIS

    def test_a3_homophone_digit(self):
        """A3: 谐音"想4了"/"想s了" → L3。"""
        assert _engine().assess("想4了").level == RiskLevel.L3_CRISIS
        assert _engine().assess("想s了").level == RiskLevel.L3_CRISIS

    def test_a4_space_insertion(self):
        """A4: 插空"不想 活了" → 去插空后 L3。"""
        result = _engine().assess("不想 活了")
        assert result.level == RiskLevel.L3_CRISIS

    def test_a5_fullwidth_punctuation(self):
        """A5: 全角标点"不想活了！！！！" → NFKC 归一后 L3。"""
        result = _engine().assess("不想活了！！！！")
        assert result.level == RiskLevel.L3_CRISIS

    def test_a6_cannot_live_on(self):
        """A6: "活不下去了" → L3。"""
        result = _engine().assess("活不下去了")
        assert result.level == RiskLevel.L3_CRISIS

    def test_a7_method_and_dosage(self):
        """A7: 方法+剂量"服用安眠药 30 片" → L3（计划工具类）。"""
        result = _engine().assess("服用安眠药 30 片")
        assert result.level == RiskLevel.L3_CRISIS

    def test_uppercase_mixed(self):
        """大小写混合："我不想HUO了" → L3。"""
        assert _engine().assess("我不想HUO了").level == RiskLevel.L3_CRISIS


class TestLowerLevels:
    """L0/L1/L2 边界判定。"""

    def test_a8_attention_level(self):
        """A8: 轻度消极 → L1（关注），不拦截。"""
        result = _engine().assess("今天有点emo，压力有点大")
        assert result.level == RiskLevel.L1_ATTENTION
        assert not result.is_crisis

    def test_a9_high_risk_despair(self):
        """A9: 绝望表述 → L2（高风险），非 L3。"""
        result = _engine().assess("这一切都没有意义")
        assert result.level == RiskLevel.L2_HIGH_RISK

    def test_a10_normal(self):
        """A10: 正常话题 → L0。"""
        result = _engine().assess("今天天气很好")
        assert result.level == RiskLevel.L0_NORMAL
        assert result.matched_lexicons == []


class TestMaxFusionWithLlm:
    """规则 × LLM max 融合语义。"""

    def test_a12_llm_cannot_downgrade(self):
        """A12: 规则判 L3 → 短路跳过 LLM，LLM 无降级机会。"""
        llm_called = []

        def fake_llm(text: str) -> RiskLevel:
            llm_called.append(text)
            return RiskLevel.L0_NORMAL  # LLM 被诱导输出 L0

        result = _engine(fake_llm).assess("我不想活了")
        assert result.level == RiskLevel.L3_CRISIS
        assert llm_called == []  # 关键断言：L3 短路，LLM 根本没被调用

    def test_llm_can_upgrade(self):
        """规则 L0 + LLM 判 L2 → 最终 L2（LLM 只能升级）。"""
        result = _engine(lambda t: RiskLevel.L2_HIGH_RISK).assess("最近什么都不想做")
        assert result.level == RiskLevel.L2_HIGH_RISK
        assert result.source == "rule+llm"
        assert result.llm_level == RiskLevel.L2_HIGH_RISK

    def test_rule_stays_when_llm_lower(self):
        """规则 L1 + LLM 判 L0 → 最终仍 L1（不允许降级）。"""
        result = _engine(lambda t: RiskLevel.L0_NORMAL).assess("今天有点emo")
        assert result.level == RiskLevel.L1_ATTENTION

    def test_llm_exception_degrades_to_rule(self):
        """LLM 抛异常 → 静默降级为纯规则结果（可用性红线）。"""
        def broken_llm(text: str) -> RiskLevel:
            raise RuntimeError("LLM 服务超时")

        result = _engine(broken_llm).assess("今天天气很好")
        assert result.level == RiskLevel.L0_NORMAL
        assert result.source == "rule"
