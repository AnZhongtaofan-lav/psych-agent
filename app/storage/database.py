# -*- coding: utf-8 -*-
"""
SQLite 连接管理与建表 DDL。

设计说明：
1. 单文件数据库 + WAL 模式：读写并发友好，崩溃后可恢复
2. 每次操作独立连接（check_same_thread=False + 连接池化简为按需新建）：
   心理服务写入频率低（每轮对话 2 条消息），新建连接成本可接受，
   换取线程安全与测试隔离的简单性
3. 外键约束显式开启（SQLite 默认关闭）
4. 建表 DDL 集中于此，幂等执行（IF NOT EXISTS）
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from app.common.logger import get_logger

logger = get_logger(__name__)


def safe_remove(path: str | os.PathLike) -> None:
    """安全删除文件：存在才删，不存在静默跳过，句柄占用也不抛。

    这是数据库文件清理的标准模式（等价于 `if os.path.exists(...): os.remove(...)`）。
    用途：
        - 测试 fixture 结束时清理临时库及其 WAL/SHM 伴生文件
        - 注意：生产库 data/psych.db 不应通过此函数删除，应改用 Database.reset()
    """
    p = Path(path)
    if p.exists():
        try:
            os.remove(p)
        except OSError:
            # Windows 下若仍有句柄占用则静默跳过
            pass

# ============================================================
# 建表 DDL（幂等）
# ------------------------------------------------------------
# 表职责：
#   sessions    会话元数据（画像/风险计数/状态机）
#   messages    对话消息（content 已脱敏 + 情绪标注）
#   risk_events 风险事件流水（安全审计核心表）
#   profiles    匿名画像聚合（无 PII 字段）
#   audit_log   脱敏动作审计（只记动作类型）
# ============================================================
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    anonymous_id   TEXT NOT NULL,
    persona_type   TEXT NOT NULL DEFAULT 'P4',
    risk_streak    INTEGER NOT NULL DEFAULT 0,
    risk_level_max INTEGER NOT NULL DEFAULT 0,
    state          TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_anonymous ON sessions(anonymous_id);

CREATE TABLE IF NOT EXISTS messages (
    message_id         TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(session_id),
    role               TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content            TEXT NOT NULL,  -- 已脱敏文本（仓储层强制保证）
    emotion_category   TEXT,
    emotion_intensity  REAL,
    emotion_confidence REAL,
    emotion_source     TEXT,
    matched_rules      TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS risk_events (
    event_id           TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(session_id),
    risk_level         INTEGER NOT NULL,
    triggered_lexicons TEXT NOT NULL DEFAULT '[]',
    is_intercepted     INTEGER NOT NULL DEFAULT 0,
    action_taken       TEXT NOT NULL,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_events_session ON risk_events(session_id, created_at);

CREATE TABLE IF NOT EXISTS profiles (
    anonymous_id      TEXT PRIMARY KEY,
    dominant_emotions TEXT NOT NULL DEFAULT '{}',
    mood_trend        TEXT NOT NULL DEFAULT '[]',
    risk_level_max    INTEGER NOT NULL DEFAULT 0,
    risk_streak       INTEGER NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    persona_type      TEXT NOT NULL DEFAULT 'P4',
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id   TEXT PRIMARY KEY,
    action     TEXT NOT NULL,           -- 脱敏动作类型（如 mask_phone）
    context    TEXT NOT NULL,           -- 脱敏发生位置（entry_middleware/repository_write）
    details    TEXT NOT NULL DEFAULT '{}',  -- 扩展 JSON（不含任何文本内容）
    created_at TEXT NOT NULL
);
"""


class Database:
    """SQLite 数据库访问对象。

    用法:
        db = Database("./data/psych.db")
        db.init()                       # 幂等建表
        with db.connect() as conn:      # 上下文管理：自动 commit/rollback
            conn.execute(...)
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        # 确保数据库文件所在目录存在（如 ./data/）
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """新建一个 SQLite 连接（调用方用 with 管理事务）。

        - check_same_thread=False：允许跨线程使用（FastAPI 线程池执行同步路由）
        - 显式开启外键（SQLite 每连接默认关闭）
        - row_factory 设为 sqlite3.Row：查询结果可按列名访问
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        """幂等初始化：建表 + WAL 模式。

        WAL 说明：Write-Ahead Logging 提升读写并发，
        且进程崩溃后数据库可自动恢复到一致状态。
        """
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
        logger.info("数据库初始化完成: path=%s mode=WAL", self.db_path)

    def drop_all(self) -> None:
        """清空所有业务表（保留数据库文件本身）。

        用途：
            1. 测试间数据重置——避免每个测试都删文件，改用重建表
            2. 运维环境"清数据但留库"的需要

        实现要点：
            - 先关外键再删表：规避 FK 依赖顺序问题（删完统一重建，约束会由 create 恢复）
            - 不删 SQLite 系统表（sqlite_*）
            - 仅操作业务表，不触碰文件系统（与 os.remove 方案互补）
        """
        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            # 查询所有业务表名（排除 sqlite_ 开头的系统表）
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]
            for name in tables:
                conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            conn.execute("PRAGMA foreign_keys = ON")
        if tables:
            logger.info("已清空 %d 张业务表: path=%s", len(tables), self.db_path)

    def reset(self) -> None:
        """重置数据库：drop_all() + init()。

        这是测试与运维推荐的清理方式——不删除任何文件，
        仅在原文件上重建表结构，避免：
            - Windows 下 WAL/SHM 句柄占用导致 os.remove 失败
            - 删除文件后目录权限/句柄泄漏问题
        """
        self.drop_all()
        self.init()
