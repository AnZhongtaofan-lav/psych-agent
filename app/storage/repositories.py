# -*- coding: utf-8 -*-
"""
仓储访问对象 —— 数据层唯一的数据读写出口。

安全红线（防御纵深第二道防线）：
    任何含自由文本的字段（当前为 messages.content）在 INSERT/UPDATE 前
    【强制】经过 anonymize() —— 即使上游（交互层中间件）已脱敏过一遍。
    这样即便未来新增旁路写库代码，持久化数据仍然安全。

    结构化字段（会话状态、情绪类别、画像统计）不含自由文本，
    无 PII 风险，不重复脱敏（在各自方法注释中说明理由）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.storage.anonymizer import AnonymizeReport, anonymize
from app.storage.audit import AuditLogger
from app.storage.database import Database
from app.storage.models import Message, Profile, RiskEvent, Session


def _now_iso() -> str:
    """统一 UTC ISO 8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """生成 UUID v4 主键。"""
    return str(uuid.uuid4())


class SessionRepository:
    """会话仓储。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, anonymous_id: str, persona_type: str = "P4") -> Session:
        """创建会话。

        安全说明：anonymous_id 是服务端生成的 UUID（无真实身份语义），
        persona_type 是受控枚举值，两者均无自由文本，无需脱敏。
        """
        now = _now_iso()
        session = Session(
            session_id=_new_id(),
            anonymous_id=anonymous_id,
            persona_type=persona_type,
            created_at=now,
            updated_at=now,
        )
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, anonymous_id, persona_type, "
                "risk_streak, risk_level_max, state, created_at, updated_at) "
                "VALUES (?, ?, ?, 0, 0, 'active', ?, ?)",
                (session.session_id, session.anonymous_id, session.persona_type,
                 session.created_at, session.updated_at),
            )
        return session

    def get(self, session_id: str) -> Session | None:
        """按 id 查询会话；不存在返回 None（由上层转 404）。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return Session(
            session_id=row["session_id"],
            anonymous_id=row["anonymous_id"],
            persona_type=row["persona_type"],
            risk_streak=row["risk_streak"],
            risk_level_max=row["risk_level_max"],
            state=row["state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_after_round(
        self,
        session_id: str,
        *,
        persona_type: str | None = None,
        risk_streak: int | None = None,
        risk_level_max: int | None = None,
        state: str | None = None,
    ) -> None:
        """一轮对话结束后更新会话元数据（部分更新，只写非 None 字段）。"""
        sets: list[str] = ["updated_at = ?"]
        params: list = [_now_iso()]
        # 动态拼装 SET 子句：字段名全部来自本方法签名（白名单），无注入风险
        if persona_type is not None:
            sets.append("persona_type = ?")
            params.append(persona_type)
        if risk_streak is not None:
            sets.append("risk_streak = ?")
            params.append(risk_streak)
        if risk_level_max is not None:
            sets.append("risk_level_max = ?")
            params.append(risk_level_max)
        if state is not None:
            sets.append("state = ?")
            params.append(state)
        params.append(session_id)
        with self._db.connect() as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = ?",
                params,
            )


class MessageRepository:
    """消息仓储 —— 自由文本唯一落库点，脱敏强制执行。"""

    def __init__(self, db: Database, audit: AuditLogger) -> None:
        self._db = db
        self._audit = audit

    def add(self, message: Message) -> Message:
        """写入一条消息；content 强制脱敏后再落库。

        脱敏语义：
            content 是唯一的自由文本字段。即使调用方已在上游脱敏，
            此处仍再执行一次（幂等：掩码文本不会再命中 PII 正则），
            保证"入库即无 PII"由数据层自身兜底。
        """
        masked, report = anonymize(message.content)
        if report.has_changes:
            # 审计只记录动作类型（mask_phone 等），不记录任何文本
            self._audit.record(report, "repository_write")
        message.content = masked

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO messages (message_id, session_id, role, content, "
                "emotion_category, emotion_intensity, emotion_confidence, "
                "emotion_source, matched_rules, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id, message.session_id, message.role,
                    message.content, message.emotion_category,
                    message.emotion_intensity, message.emotion_confidence,
                    message.emotion_source, message.matched_rules,
                    message.created_at or _now_iso(),
                ),
            )
        return message

    def list_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        """按会话倒序列出最近消息（供上下文构建；均已是脱敏文本）。"""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            Message(
                message_id=r["message_id"], session_id=r["session_id"],
                role=r["role"], content=r["content"],
                emotion_category=r["emotion_category"],
                emotion_intensity=r["emotion_intensity"],
                emotion_confidence=r["emotion_confidence"],
                emotion_source=r["emotion_source"],
                matched_rules=r["matched_rules"], created_at=r["created_at"],
            )
            for r in rows
        ]


class RiskEventRepository:
    """风险事件仓储 —— 安全审计流水。

    安全说明：triggered_lexicons 存储的是词典条目标签
    （如 "自杀意念:不想活"），来自固定词典而非用户文本，无 PII 风险。
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, event: RiskEvent) -> None:
        """记录一条风险事件。"""
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO risk_events (event_id, session_id, risk_level, "
                "triggered_lexicons, is_intercepted, action_taken, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id, event.session_id, event.risk_level,
                    event.triggered_lexicons, int(event.is_intercepted),
                    event.action_taken, event.created_at or _now_iso(),
                ),
            )


class ProfileRepository:
    """画像仓储 —— 按匿名 id 聚合行为统计。

    安全说明：本表全部字段为受控枚举/数值/类别名 JSON，
    结构上不含自由文本，因此无 PII 风险，不做脱敏处理。
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, anonymous_id: str) -> Profile | None:
        """只读查询画像；不存在返回 None（不创建，供 404 判定）。

        与 get_or_create 的区别：查询接口不允许"读时写入"，
        避免对不存在的匿名 id 探测产生数据足迹。
        """
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE anonymous_id = ?", (anonymous_id,)
            ).fetchone()
        if row is None:
            return None
        return Profile(
            anonymous_id=row["anonymous_id"],
            dominant_emotions=row["dominant_emotions"],
            mood_trend=row["mood_trend"],
            risk_level_max=row["risk_level_max"],
            risk_streak=row["risk_streak"],
            interaction_count=row["interaction_count"],
            persona_type=row["persona_type"],
            updated_at=row["updated_at"],
        )

    def get_or_create(self, anonymous_id: str) -> Profile:
        """获取画像；不存在则创建默认画像（P4 / 无情绪记录）。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE anonymous_id = ?", (anonymous_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO profiles (anonymous_id, dominant_emotions, "
                    "mood_trend, risk_level_max, risk_streak, interaction_count, "
                    "persona_type, updated_at) VALUES (?, '{}', '[]', 0, 0, 0, 'P4', ?)",
                    (anonymous_id, _now_iso()),
                )
                return Profile(anonymous_id=anonymous_id, updated_at=_now_iso())
        return Profile(
            anonymous_id=row["anonymous_id"],
            dominant_emotions=row["dominant_emotions"],
            mood_trend=row["mood_trend"],
            risk_level_max=row["risk_level_max"],
            risk_streak=row["risk_streak"],
            interaction_count=row["interaction_count"],
            persona_type=row["persona_type"],
            updated_at=row["updated_at"],
        )

    def update(
        self,
        anonymous_id: str,
        *,
        dominant_emotions: dict[str, float] | None = None,
        mood_trend: list[str] | None = None,
        risk_level_max: int | None = None,
        risk_streak: int | None = None,
        persona_type: str | None = None,
        interaction_delta: int = 0,
    ) -> None:
        """更新画像（调用方传完整聚合结果，此处只负责持久化）。"""
        current = self.get_or_create(anonymous_id)
        emotions_json = (
            json.dumps(dominant_emotions, ensure_ascii=False)
            if dominant_emotions is not None else current.dominant_emotions
        )
        trend_json = (
            json.dumps(mood_trend, ensure_ascii=False)
            if mood_trend is not None else current.mood_trend
        )
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE profiles SET dominant_emotions = ?, mood_trend = ?, "
                "risk_level_max = ?, risk_streak = ?, persona_type = ?, "
                "interaction_count = ?, updated_at = ? WHERE anonymous_id = ?",
                (
                    emotions_json, trend_json,
                    risk_level_max if risk_level_max is not None else current.risk_level_max,
                    risk_streak if risk_streak is not None else current.risk_streak,
                    persona_type if persona_type is not None else current.persona_type,
                    current.interaction_count + interaction_delta,
                    _now_iso(), anonymous_id,
                ),
            )


# ------------------------------------------------------------
# 匿名报告再导出：供上层类型标注使用
# ------------------------------------------------------------
__all__ = [
    "AnonymizeReport",
    "MessageRepository",
    "ProfileRepository",
    "RiskEventRepository",
    "SessionRepository",
]
