# -*- coding: utf-8 -*-
"""
回复生成器 —— 模板库（规则模式）与 LLM 生成（增强模式）。

双模式设计：
1. 【模板模式（默认，永远可用）】
   按风险等级 × 画像选择本地话术模板 —— 确定性、零延迟、零外部依赖
2. 【LLM 增强模式（可选）】
   仅在 L0/L1 且画像允许时调用 LLM；输出必须通过出口安检
   （screen_llm_reply），不安全/失败/超时 → 一律回退模板

安全约束（LLM 提示词层面，与 client.py 的系统提示词双保险）：
   - 用户提示词中只包含"策略方向 + 情绪标注"，不包含任何
     可能诱导复述危机内容的历史原文
"""

from __future__ import annotations

import random
from collections.abc import Callable

from app.common.constants import PersonaType
from app.core.emotion.emotion_engine import EmotionResult
from app.core.profile.personas import PERSONA_REGISTRY
from app.core.risk.interceptors import screen_llm_reply
from app.core.risk.risk_engine import RiskAssessment

# LLM 完成函数签名：输入组装好的提示词 → 回复文本或 None（失败）
LlmCompleteFn = Callable[[str], "str | None"]


class ReplyGenerator:
    """回复生成器。"""

    def __init__(self, llm_fn: LlmCompleteFn | None = None) -> None:
        # llm_fn 为 None 表示未配置 LLM（纯模板模式）
        self._llm_fn = llm_fn

    # ============================================================
    # 模板库
    # ------------------------------------------------------------
    # 模板占位符：{topic} = 命中的画像信号词（无则用通用词）
    # 设计原则：先共情确认，再给方向；不评判、不说教
    # ============================================================
    _L0_TEMPLATES: dict[PersonaType, tuple[str, ...]] = {
        PersonaType.P1_STUDENT: (
            "听起来{topic}这件事让你压力不小。想具体说说最近的情况吗？"
            "比如是什么时候开始觉得吃力的？",
            "学业上的紧绷感很磨人，你能说出来已经很不容易了。"
            "最近{topic}上最让你喘不过气的是哪一块？",
        ),
        PersonaType.P2_WORKER: (
            "工作里的消耗常常是无声的，{topic}听起来是压垮你的那一环。"
            "愿意展开讲讲吗？",
            "听起来{topic}让你积攒了不少疲惫。最近加班/沟通的节奏具体是什么样的？",
        ),
        PersonaType.P4_GENERAL: (
            "谢谢你愿意跟我说这些。想多了解一下：这种感受最近频繁出现吗？",
            "我在听。你说的事情里，哪一部分最让你在意？",
        ),
    }

    _L1_TEMPLATES: tuple[str, ...] = (
        "听起来这段时间你过得不容易，有这些感受是很正常的。"
        "愿意多说说吗？我想更完整地了解你的处境。",
        "你的感受值得被认真对待，不着急，慢慢说。"
        "这种感觉最近是从什么时候开始变得明显的？",
        "谢谢你信任我。不管是什么让你难受，都可以在这里说出来。"
        "最近有没有哪件事让你特别有压力？",
    )

    # L2 高风险：关怀 + 建议就医（陪伴模式：绝不给建议清单）
    _L2_TEMPLATES: dict[PersonaType, tuple[str, ...]] = {
        PersonaType.P1_STUDENT: (
            "听到你承受着这些，我很心疼。学业上的重压不该由你一个人扛着。"
            "如果这种沉重感一直在，我真心建议你和学校心理咨询中心"
            "或医院心理科聊一聊——那不是脆弱，是对自己负责。"
            "现在，可以先跟我说说你的感受吗？我会陪着你。",
        ),
        PersonaType.P2_WORKER: (
            "你已经在很努力地撑着了，这些疲惫是真实的、值得被看见的。"
            "如果情绪的重量持续压着你，建议你考虑预约医院心理科"
            "或专业心理咨询——这和看感冒一样正常。"
            "此刻你想聊什么都可以，我在听。",
        ),
        # P3 与 P4 共用通用版（P3 画像在本轮非危机时也走陪伴模式）
        PersonaType.P3_CRISIS: (
            "我能感觉到你现在心里很沉重。你的感受很重要，你也很重要。"
            "我建议你尽快联系专业的心理支持——医院心理科或心理援助热线都可以，"
            "专业人士能给你更可靠的帮助。在这里，你也可以先跟我说说，我陪着你。",
        ),
        PersonaType.P4_GENERAL: (
            "我能感觉到你现在心里很沉重。你的感受很重要，你也很重要。"
            "如果这种状态持续了一段时间，建议你和医院心理科或专业咨询师聊聊。"
            "在这里，你也可以先跟我说说，我陪着你。",
        ),
    }

    def generate_template_reply(
        self,
        risk: RiskAssessment,
        persona: PersonaType,
        emotion: EmotionResult,
        signals: list[str],
    ) -> str:
        """按 (风险等级, 画像) 从模板库生成回复（规则模式主路径）。"""
        topic = "这些" if not signals else "、".join(signals[:3])

        if risk.level == 2:  # L2 高风险：关怀 + 就医建议（按画像细分）
            templates = self._L2_TEMPLATES.get(persona) or self._L2_TEMPLATES[PersonaType.P4_GENERAL]
            return random.choice(templates)

        if risk.level == 1:  # L1 关注：引导倾诉
            return random.choice(self._L1_TEMPLATES)

        # L0 正常：按画像选择模板；未注册画像回退 P4
        templates = self._L0_TEMPLATES.get(persona) or self._L0_TEMPLATES[PersonaType.P4_GENERAL]
        return random.choice(templates).format(topic=topic)

    def generate_llm_reply(
        self,
        user_text: str,
        risk: RiskAssessment,
        persona: PersonaType,
        emotion: EmotionResult,
    ) -> str | None:
        """尝试用 LLM 生成回复（增强模式）；任何不安全/失败 → None。

        启用条件（调用方 strategy 已保证，此处再校验一次 —— 防御纵深）：
            - LLM 已配置
            - 风险等级 ≤ L1（L2/L3 一律模板，杜绝 LLM 在高危场景发挥）
            - 画像允许（P3 恒为模板）
        出口安检：screen_llm_reply 不通过 → 丢弃，返回 None
        """
        if self._llm_fn is None:
            return None
        if risk.level >= 2:
            return None
        if not PERSONA_REGISTRY[persona].allow_llm_reply:
            return None

        # 组装提示词：只给"策略方向 + 情绪标注"，不给用户原文以外的历史
        definition = PERSONA_REGISTRY[persona]
        prompt = (
            f"用户刚刚对心理支持助手说了一句话。请以共情、不评判的语气回应，"
            f"限 150 字以内，以一句开放式提问结尾。\n"
            f"用户画像方向：{definition.strategy}（语气：{definition.tone}）。\n"
            f"检测到的情绪：{emotion.category.value}（强度 {emotion.intensity:.1f}）。\n"
            f"硬性约束：绝对不要提及任何自我伤害相关的方法、工具或行为；"
            f"不要诊断；不要给清单式建议。\n"
            f"用户说：{user_text}"
        )
        try:
            reply = self._llm_fn(prompt)
        except Exception:  # noqa: BLE001 —— LLM 故障必须静默回退
            return None
        if not reply:
            return None
        # 出口安检：LLM 输出再过 L3 规则（防被上下文诱导生成有害内容）
        if not screen_llm_reply(reply):
            return None
        return reply
