# -*- coding: utf-8 -*-
"""
四类用户画像定义（需求分析产物，见架构方案第二节）。

画像 = 识别信号 + 服务策略。本模块只声明"是什么"，
"怎么判定"在 profile_builder.py，"怎么用"在 dialogue/strategy.py。

判定优先级（在 profile_builder 中实现，此处仅约定）：
    1. P3 危机倾向 —— 最高优先级：命中 L2/L3 或历史 risk_level_max ≥ 2 时
       强制覆盖，阻断一切常规建议类回复
    2. P1/P2 —— 按信号词命中数推断（学业词 vs 职场词）
    3. P4 —— 兜底默认
"""

from __future__ import annotations

from dataclasses import dataclass

from app.common.constants import PersonaType


@dataclass(frozen=True)
class PersonaProfile:
    """画像定义（不可变配置）。

    属性:
        persona: 画像枚举
        signals: 识别信号词元组（在归一化文本上做子串匹配）
        strategy: 服务策略一句话概括（供回复生成器选择模板族）
        tone: 语气基调
        forbid: 禁止行为（安全约束，回复生成器必须遵守）
        allow_llm_reply: 是否允许 LLM 生成回复（P3 恒为 False：
            危机画像下回复只允许模板产出，杜绝 LLM 不可控输出）
    """

    persona: PersonaType
    signals: tuple[str, ...]
    strategy: str
    tone: str
    forbid: tuple[str, ...]
    allow_llm_reply: bool = True


# ------------------------------------------------------------
# P1 学业压力学生：考试/挂科/考研等学业场景词
# ------------------------------------------------------------
P1_STUDENT = PersonaProfile(
    persona=PersonaType.P1_STUDENT,
    signals=(
        "考试", "挂科", "补考", "考研", "高考", "绩点", "成绩",
        "作业", "论文", "导师", "宿舍", "同学", "老师", "开学",
        "复习", "上课", "学业", "保研", "期末",
    ),
    strategy="共情 → 情绪命名 → 学业时间管理技巧 → 校内资源引导",
    tone="亲和、平等、不说教",
    forbid=("说教式鼓励（如'你要坚强'）", "评判成绩对错"),
)

# ------------------------------------------------------------
# P2 职场焦虑者：加班/裁员/绩效等职场场景词
# ------------------------------------------------------------
P2_WORKER = PersonaProfile(
    persona=PersonaType.P2_WORKER,
    signals=(
        "加班", "裁员", "绩效", "老板", "领导", "辞职", "跳槽",
        "上班", "职场", "开会", "周报", "kpi", "35岁", "失业",
        "面试", "工作", "项目", "工资", "年终奖",
    ),
    strategy="认知重评 → 边界设定 → 压力拆解",
    tone="专业、平等、结构化建议",
    forbid=("评判职业选择", "空洞鸡汤"),
)

# ------------------------------------------------------------
# P3 危机倾向用户：不靠信号词判定（由风险等级强制），
# 此处 signals 留空仅作占位；allow_llm_reply 必须为 False
# ------------------------------------------------------------
P3_CRISIS = PersonaProfile(
    persona=PersonaType.P3_CRISIS,
    signals=(),
    strategy="策略覆盖：危机话术 + 热线转介 + 陪伴式语言，阻断常规建议",
    tone="温和、直接、不回避死亡话题",
    forbid=(
        "任何建议清单",
        "讨论自伤方法细节",
        "'你想开点'式劝解",
    ),
    allow_llm_reply=False,
)

# ------------------------------------------------------------
# P4 普通情绪疏导用户：无显著场景信号时的默认画像
# ------------------------------------------------------------
P4_GENERAL = PersonaProfile(
    persona=PersonaType.P4_GENERAL,
    signals=(),
    strategy="倾听 → 开放式提问 → 情绪验证 → 自助小练习",
    tone="轻松、支持性",
    forbid=("过度病理化", "强行升级话题严重性"),
)

# 画像注册表：persona 值 → 定义（供各模块按枚举取配置）
PERSONA_REGISTRY: dict[PersonaType, PersonaProfile] = {
    PersonaType.P1_STUDENT: P1_STUDENT,
    PersonaType.P2_WORKER: P2_WORKER,
    PersonaType.P3_CRISIS: P3_CRISIS,
    PersonaType.P4_GENERAL: P4_GENERAL,
}
