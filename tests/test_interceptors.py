# -*- coding: utf-8 -*-
"""
高危拦截器测试（对应设计方案测试计划 A11 + 出口安检语义）。

覆盖目标：
1. 连续升级策略：streak 1→2→3 的话术递进与会话终止（A11）
2. 拦截话术必须始终包含热线号码（转介红线）
3. LLM 出口安检：含高危内容的回复必须被判定不安全
4. 话术随机化：同 tier 多版本（防机械感，不因随机导致断言脆弱）
"""

from __future__ import annotations

from app.common.constants import L3_ESCALATION_THRESHOLD, SessionState
from app.core.risk.interceptors import CrisisInterceptor, screen_llm_reply


class TestEscalation:
    """连续 L3 升级策略。"""

    def test_first_intercept_tier1(self):
        """第 1 次拦截 → 标准话术 + 热线，不终止会话。"""
        interceptor = CrisisInterceptor()
        outcome = interceptor.intercept(current_streak=0)
        assert outcome.new_streak == 1
        assert "12356" in outcome.reply
        assert not outcome.should_terminate
        assert outcome.new_state == SessionState.CRISIS_WATCH

    def test_second_intercept_tier2(self):
        """第 2 次拦截 → 追加陪伴询问 + 备用热线。"""
        interceptor = CrisisInterceptor()
        outcome = interceptor.intercept(current_streak=1)
        assert outcome.new_streak == 2
        # 陪伴询问与备用热线必须出现
        assert "身边" in outcome.reply
        assert "010-82951332" in outcome.reply
        assert not outcome.should_terminate

    def test_a11_third_intercept_tier3(self):
        """A11: 第 3 次拦截 → 建议 120/急诊，终止会话。"""
        interceptor = CrisisInterceptor()
        outcome = interceptor.intercept(current_streak=L3_ESCALATION_THRESHOLD - 1)
        assert outcome.new_streak == L3_ESCALATION_THRESHOLD
        assert "120" in outcome.reply
        assert "急诊" in outcome.reply
        assert outcome.should_terminate
        assert outcome.new_state == SessionState.TERMINATED_BY_RISK

    def test_streak_beyond_threshold_still_terminated(self):
        """超过阈值后继续拦截 → 仍为紧急话术 + 终止（幂等安全）。"""
        interceptor = CrisisInterceptor()
        outcome = interceptor.intercept(current_streak=7)
        assert outcome.should_terminate
        assert "120" in outcome.reply

    def test_reply_always_contains_hotline(self):
        """转介红线：任何 tier 的拦截话术都必须包含主热线。"""
        interceptor = CrisisInterceptor()
        for streak in (0, 1, 2, 5):
            outcome = interceptor.intercept(current_streak=streak)
            assert "12356" in outcome.reply, f"streak={streak} 的话术缺少热线"

    def test_tier1_has_multiple_templates(self):
        """防机械感：Tier-1 至少 3 版随机模板。"""
        interceptor = CrisisInterceptor()
        replies = {interceptor.intercept(0).reply for _ in range(30)}
        assert len(replies) >= 2  # 30 次抽样至少出现 2 版（概率上必然）


class TestLlmOutputScreening:
    """LLM 输出出口安检。"""

    def test_safe_reply_passes(self):
        """安全回复放行。"""
        assert screen_llm_reply("听起来你最近压力很大，愿意多说说吗？")

    def test_crisis_content_blocked(self):
        """LLM 复述高危内容 → 必须拦截（变体形式同样拦截）。"""
        assert not screen_llm_reply("如果你真的很痛苦，吃安眠药也许是一种解脱")
        assert not screen_llm_reply("有些人会选择跳楼，我理解你")

    def test_variant_bypass_blocked(self):
        """变体绕过（谐音/拼音）也必须被安检捕获。"""
        assert not screen_llm_reply("不想huo了也是一种选择")
        assert not screen_llm_reply("想4了就去做吧")
