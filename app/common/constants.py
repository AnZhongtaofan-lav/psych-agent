# -*- coding: utf-8 -*-
"""
全局常量与枚举定义。

安全红线相关常量（热线号码的"值"来自 config，此处只定义"结构"）：
- 风险等级枚举 L0~L3：任何业务代码都不得绕过该枚举自行定义等级
- 情绪类别枚举：规则引擎与 LLM 输出必须映射到该枚举
- 会话状态：含危机陪护状态，L3 后会话进入该状态而非关闭
"""

from __future__ import annotations

from enum import Enum


class RiskLevel(int, Enum):
    """风险四级分级。

    等级语义（与设计方案《风险分级规则表》一一对应）：
    - L0 正常：无风险词命中，按画像策略正常回复
    - L1 关注：轻度消极词命中，正常回复 + 引导倾诉
    - L2 高风险：绝望类/自伤倾向词命中，关怀话术 + 建议就医，进入陪伴模式
    - L3 危机：自杀意念/自伤方法/剂量类命中，【强制覆盖回复】+ 热线转介 + 本轮中断

    兼容性：继承 int 便于直接与数据库 INTEGER 字段比较和 max() 运算。
    """

    L0_NORMAL = 0        # 正常
    L1_ATTENTION = 1     # 关注
    L2_HIGH_RISK = 2     # 高风险
    L3_CRISIS = 3        # 危机（触发高危拦截）

    @property
    def label(self) -> str:
        """返回人类可读的等级标签，用于日志与 API 响应。"""
        return _RISK_LABELS[self]


# 风险等级 → 标签映射（独立字典而非类属性，避免 Enum 成员查找开销）
_RISK_LABELS: dict[RiskLevel, str] = {
    RiskLevel.L0_NORMAL: "正常",
    RiskLevel.L1_ATTENTION: "关注",
    RiskLevel.L2_HIGH_RISK: "高风险",
    RiskLevel.L3_CRISIS: "危机",
}


class EmotionCategory(str, Enum):
    """情绪类别枚举（规则引擎与 LLM 输出的统一出口类型）。

    设计说明：类别集合是"规则引擎能可靠识别"与"LLM 可细分"的最大公约数，
    LLM 返回的更细类别（如"委屈"）会归并到最近的粗类别（如"悲伤"）。
    """

    ANXIETY = "焦虑"       # 焦虑/紧张/恐惧类
    DEPRESSION = "抑郁"    # 抑郁/低落/无望类
    ANGER = "愤怒"         # 愤怒/烦躁/怨恨类
    SADNESS = "悲伤"       # 悲伤/委屈/难过类
    CALM = "平静"          # 平静/放松类
    NEUTRAL = "中性"       # 无法识别或无情绪色彩


class EmotionSource(str, Enum):
    """情绪识别结果来源。

    - rule：仅规则引擎
    - llm：仅 LLM（理论上不出现，LLM 只做增强）
    - rule+llm：两者融合（取置信度更高/类别更强者）
    """

    RULE = "rule"
    LLM = "llm"
    RULE_LLM = "rule+llm"


class PersonaType(str, Enum):
    """用户画像四分类（见设计方案第二节）。

    判定优先级（在 profile_builder 中实现）：
    1. 命中 L2/L3 规则或历史 risk_level_max >= 2 → 强制 P3（覆盖一切）
    2. 否则按词类 + 情绪滚动统计推断 P1/P2/P4
    """

    P1_STUDENT = "P1"    # 学业压力学生
    P2_WORKER = "P2"     # 职场焦虑者
    P3_CRISIS = "P3"     # 危机倾向用户（策略覆盖：阻断常规建议）
    P4_GENERAL = "P4"    # 普通情绪疏导用户


class SessionState(str, Enum):
    """会话状态。

    - active：正常会话
    - crisis_watch：危机陪护状态（L3 触发后进入；会话不关闭但处于高危看护）
    - ended：用户主动结束
    - terminated_by_risk：连续 L3 >= 3 轮后系统终止（建议线下急救；画像保留危机标记）
    """

    ACTIVE = "active"
    CRISIS_WATCH = "crisis_watch"
    ENDED = "ended"
    TERMINATED_BY_RISK = "terminated_by_risk"


class MessageRole(str, Enum):
    """消息角色：user = 用户输入；assistant = 智能体回复。"""

    USER = "user"
    ASSISTANT = "assistant"


# ------------------------------------------------------------
# 风险响应动作常量（risk_events.action_taken 字段取值）
# 注意：这些值会入库，修改前必须考虑数据兼容
# ------------------------------------------------------------
ACTION_NORMAL = "normal"                    # L0：正常回复
ACTION_GUIDE = "guide"                      # L1：引导倾诉
ACTION_MEDICAL = "medical"                  # L2：建议就医
ACTION_INTERCEPT_HOTLINE = "intercept_hotline"  # L3：拦截 + 热线转介

# L3 连续升级阈值：达到该轮数后建议拨打急救电话并终止会话
L3_ESCALATION_THRESHOLD = 3

# 用户画像 mood_trend 滚动窗口长度：只保留最近 20 条情绪记录
MOOD_TREND_WINDOW = 20
