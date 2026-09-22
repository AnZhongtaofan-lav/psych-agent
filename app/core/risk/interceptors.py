# -*- coding: utf-8 -*-
"""
L3 高危拦截器 —— 危机场景的强制响应模块。

核心职责（安全红线，任何上层模块都不得绕过）：
1. 【覆盖回复】L3 命中后，本轮回复必须是拦截话术，
   完全取代（override）对话策略生成的常规回复
2. 【热线转介】拦截话术必须包含心理援助热线（12356 等，配置化）
3. 【连续升级】连续 L3 轮数（risk_streak）达到阈值后逐级升级：
       streak=1  标准危机话术 + 热线（3 版随机化，防机械感）
       streak=2  追加"身边是否有人陪伴"询问 + 再次强调热线
       streak>=3 建议拨打 120/110 或前往急诊，会话置 terminated_by_risk
4. 【出口安检】提供 screen_llm_reply()：LLM 生成的回复文本必须
   再过一遍 L3 规则，命中则判定不安全（供上层丢弃回退）

设计取舍：
    - 拦截路径【不调用 LLM】：话术全部来自本地模板（确定性 + 低延迟）
    - 误报优于漏报：拦截话术对非危机用户只是"多一句关怀"，
      而漏报的代价不可接受
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.common.constants import L3_ESCALATION_THRESHOLD, RiskLevel, SessionState
from app.core.normalizer import normalize
from app.core.risk.risk_rules import RiskRules


@dataclass
class InterceptOutcome:
    """拦截结果。

    属性:
        reply: 拦截话术（本轮最终回复，覆盖一切常规生成）
        new_streak: 累加后的连续高危轮数（调用方持久化到会话）
        should_terminate: 是否应终止会话（streak >= 3 → True）
        new_state: 会话应进入的状态（crisis_watch / terminated_by_risk）
    """

    reply: str
    new_streak: int
    should_terminate: bool
    new_state: SessionState


class CrisisInterceptor:
    """危机拦截器：模板话术 + 升级策略。

    参数（来自 config，支持多地区部署覆盖）:
        hotline_primary: 主要热线（默认 12356）
        hotline_secondary: 备用热线
        emergency_number: 紧急医疗电话（默认 120）
    """

    def __init__(
        self,
        hotline_primary: str = "12356",
        hotline_secondary: str = "010-82951332",
        emergency_number: str = "120",
    ) -> None:
        self.hotline_primary = hotline_primary
        self.hotline_secondary = hotline_secondary
        self.emergency_number = emergency_number

    # ------------------------------------------------------------
    # 话术模板库
    # ------------------------------------------------------------
    # Tier-1 标准危机话术（3 版随机化：重复触发时避免机械复读）
    _TIER1_TEMPLATES: tuple[str, ...] = (
        "我听到了你此刻的痛苦，这很重要。你的安全是第一位的。"
        "请立即拨打全国心理援助热线 {primary}（24 小时免费），"
        "有专业的咨询师陪你一起面对。如果你愿意，也可以告诉我现在发生了什么，我会一直在这里。",
        "谢谢你愿意把这份痛苦说出来。现在，我想请你先做一件事："
        "拨打心理援助热线 {primary}，那里有专业的人可以立刻帮到你。"
        "你不需要独自扛着这一切，我也可以继续陪你说说话。",
        "你现在的感受值得被认真对待。请马上联系心理援助热线 {primary}，"
        "这是 24 小时免费的专业支持渠道。"
        "挂断之前，如果你愿意，可以跟我多说说你的处境。",
    )

    # Tier-2 追加段：陪伴询问 + 再次强调热线
    _TIER2_SUFFIX: str = (
        "另外我想确认：此刻你的身边有没有可以陪着你的人？"
        "如果有人在，请让他们陪着你；如果暂时没有，请一定先拨通 {primary}，"
        "或联系备用热线 {secondary}。你不是一个人。"
    )

    # Tier-3 紧急升级话术（连续高危达到阈值）
    _TIER3_TEMPLATES: tuple[str, ...] = (
        "情况很紧急，我非常担心你现在的安全。"
        "请立即拨打急救电话 {emergency}，或前往最近的医院急诊科。"
        "同时请拨打心理援助热线 {primary}。现在就行动，好吗？你的生命很重要。",
        "我必须直接地说：请现在就拨打 {emergency} 或让身边的人送你去最近的医院急诊。"
        "心理援助热线 {primary} 也可以立刻接通专业人员。"
        "此刻你的安全高于一切，请马上行动。",
    )

    def intercept(self, current_streak: int) -> InterceptOutcome:
        """执行拦截并生成升级话术。

        参数:
            current_streak: 拦截前会话的连续高危轮数（0 表示本轮是第 1 次）

        返回:
            InterceptOutcome（调用方负责将 new_streak/new_state 持久化）
        """
        new_streak = current_streak + 1

        if new_streak >= L3_ESCALATION_THRESHOLD:
            # Tier-3：紧急升级 → 建议急救 + 终止会话
            template = random.choice(self._TIER3_TEMPLATES)
            reply = template.format(
                emergency=self.emergency_number, primary=self.hotline_primary
            )
            return InterceptOutcome(
                reply=reply,
                new_streak=new_streak,
                should_terminate=True,
                new_state=SessionState.TERMINATED_BY_RISK,
            )

        if new_streak == 2:
            # Tier-2：标准话术 + 陪伴询问
            reply = random.choice(self._TIER1_TEMPLATES).format(
                primary=self.hotline_primary
            ) + self._TIER2_SUFFIX.format(
                primary=self.hotline_primary, secondary=self.hotline_secondary
            )
            return InterceptOutcome(
                reply=reply,
                new_streak=new_streak,
                should_terminate=False,
                new_state=SessionState.CRISIS_WATCH,
            )

        # Tier-1：标准危机话术（第 1 次触发）
        reply = random.choice(self._TIER1_TEMPLATES).format(
            primary=self.hotline_primary
        )
        return InterceptOutcome(
            reply=reply,
            new_streak=new_streak,
            should_terminate=False,
            new_state=SessionState.CRISIS_WATCH,
        )


# ============================================================
# LLM 输出出口安检（第二道内容安全防线）
# ============================================================

# 模块级规则匹配器：仅用于 L3 文本筛查（RiskRules 内部有缓存，无重复加载开销）
_SCREEN_RULES = RiskRules()


def screen_llm_reply(reply_text: str) -> bool:
    """筛查 LLM 生成的回复是否安全（出口二次安检）。

    判定：回复文本经归一化后若命中 L3 规则 → 不安全。
    （LLM 可能被对话上下文诱导复述高危内容，例如"那我是不是该..."；

    返回:
        True = 安全，可以返回给用户；False = 不安全，调用方必须丢弃
        并回退到本地模板话术。
    """
    normalized = normalize(reply_text)
    result = _SCREEN_RULES.match(normalized)
    return result.level < RiskLevel.L3_CRISIS.value
