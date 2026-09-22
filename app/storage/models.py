# -*- coding: utf-8 -*-
"""
数据模型定义（纯 dataclass，不绑定 ORM）。

设计说明：
1. 使用标准库 dataclass 而非 SQLAlchemy：SQLite 场景下保持零依赖、可控
2. 时间戳统一存 ISO 8601 文本（SQLite 无原生日期类型，文本可读且可排序）
3. 安全红线：
   - Message.content 存入前必须已脱敏（由仓储层强制，模型层只是声明语义）
   - Profile 不含任何 PII 字段（结构上杜绝画像表泄露身份信息）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Session:
    """会话实体（sessions 表）。

    属性:
        session_id: UUID，服务端生成
        anonymous_id: 匿名用户标识（UUID，全程无真实身份）
        persona_type: 当前画像 P1~P4
        risk_streak: 连续高危（L3）轮数，用于升级策略
        risk_level_max: 本会话历史最高风险等级
        state: 会话状态（active/crisis_watch/ended/terminated_by_risk）
    """

    session_id: str
    anonymous_id: str
    persona_type: str = "P4"
    risk_streak: int = 0
    risk_level_max: int = 0
    state: str = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Message:
    """消息实体（messages 表）。

    安全语义:
        content 必须是脱敏后文本；仓储层在 INSERT 前强制调用脱敏器，
        即使调用方传入原文也不会落库（防御纵深）。

    情绪标注字段（可空）:
        emotion_category / emotion_intensity / emotion_confidence / emotion_source
        matched_rules: 命中的风险规则 id JSON 数组（可空）
    """

    message_id: str
    session_id: str
    role: str  # user / assistant
    content: str  # 已脱敏
    emotion_category: str | None = None
    emotion_intensity: float | None = None
    emotion_confidence: float | None = None
    emotion_source: str | None = None
    matched_rules: str | None = None
    created_at: str = ""


@dataclass
class RiskEvent:
    """风险事件实体（risk_events 表）。

    每一轮对话的风险判定结果都会记录一条，构成可审计的安全事件流：
    - triggered_lexicons: 命中的词典条目 JSON（如 ["自杀意念:不想活"]）
    - is_intercepted: 是否触发了 L3 强制覆盖回复
    - action_taken: normal / guide / medical / intercept_hotline
    """

    event_id: str
    session_id: str
    risk_level: int
    triggered_lexicons: str
    is_intercepted: bool
    action_taken: str
    created_at: str = ""


@dataclass
class Profile:
    """用户画像实体（profiles 表，按 anonymous_id 一行）。

    安全红线：本表【不含任何 PII 字段】——只有行为统计与情绪聚合。
    属性:
        dominant_emotions: JSON {"焦虑": 0.62, ...} 滚动加权均值
        mood_trend: JSON 最近 20 条情绪类别列表（截断防膨胀）
        risk_level_max: 历史最高风险等级（用于 P3 画像强制判定）
        risk_streak: 连续高危轮数
    """

    anonymous_id: str
    dominant_emotions: str = "{}"
    mood_trend: str = "[]"
    risk_level_max: int = 0
    risk_streak: int = 0
    interaction_count: int = 0
    persona_type: str = "P4"
    updated_at: str = ""


@dataclass
class AuditLog:
    """脱敏审计实体（audit_log 表）。

    只记录"何时对何上下文执行了何类脱敏动作"，绝记录：
    - 原文片段（禁止）
    - 掩码后的文本（也禁止：掩码文本可能与后续数据交叉还原）
    """

    audit_id: str
    action: str            # 如 mask_phone
    context: str           # 脱敏发生位置：entry_middleware / repository_write
    created_at: str = ""
    details: str = field(default="{}")  # 扩展 JSON（不含任何文本内容）
