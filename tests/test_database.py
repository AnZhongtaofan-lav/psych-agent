# -*- coding: utf-8 -*-
"""
Database 清理机制测试（drop_all / reset / 安全删除）。

验证目标：
1. drop_all() 清空所有业务表但保留数据库文件
2. reset() = drop_all + init，重建后表结构完整、外键约束恢复
3. 清理后可正常写入数据（FK 约束生效）
4. conftest 的 _safe_remove 在文件不存在时不抛异常
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.storage.database import Database, safe_remove


class TestDropAll:
    """drop_all: 清空业务表，保留文件与 sqlite 系统表。"""

    def test_drop_all_removes_business_tables(self, test_db):
        test_db.init()
        # 先插一条数据证明表里有东西
        with test_db.connect() as conn:
            conn.execute("INSERT INTO sessions (session_id, anonymous_id, created_at, updated_at) VALUES ('s1','a1','t','t')")

        test_db.drop_all()

        with test_db.connect() as conn:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
        assert tables == []

    def test_drop_all_keeps_db_file(self, test_db):
        """drop_all 不删除数据库文件本身。"""
        test_db.init()
        path = Path(test_db.db_path)
        assert path.exists()
        test_db.drop_all()
        assert path.exists(), "drop_all 不应删除数据库文件"

    def test_drop_all_on_empty_db_is_safe(self, test_db):
        """对空库（无业务表）执行 drop_all 不抛异常。"""
        # test_db fixture 不自动 init，此时只有 sqlite 系统表
        test_db.drop_all()  # 应静默成功


class TestReset:
    """reset: drop_all + init，重建后可正常使用。"""

    def test_reset_recreates_all_tables(self, test_db):
        test_db.init()
        test_db.reset()
        with test_db.connect() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        assert tables == {"sessions", "messages", "risk_events", "profiles", "audit_log"}

    def test_reset_clears_data(self, test_db):
        """reset 后所有业务表数据被清空。"""
        test_db.init()
        with test_db.connect() as conn:
            conn.execute("INSERT INTO sessions (session_id, anonymous_id, created_at, updated_at) VALUES ('s1','a1','t','t')")

        test_db.reset()

        with test_db.connect() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert cnt == 0

    def test_reset_restores_foreign_key_constraint(self, test_db):
        """reset 后外键约束恢复：插入无对应 session 的 message 应失败。"""
        test_db.init()
        test_db.reset()
        with test_db.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO messages (message_id, session_id, role, content, created_at) "
                    "VALUES ('m1','nonexistent-session','user','hi','t')"
                )

    def test_reset_allows_valid_write_after(self, test_db):
        """reset 后可正常写入符合外键的数据。"""
        test_db.init()
        test_db.reset()
        with test_db.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, anonymous_id, created_at, updated_at) "
                "VALUES ('s1','a1','t','t')"
            )
            conn.execute(
                "INSERT INTO messages (message_id, session_id, role, content, created_at) "
                "VALUES ('m1','s1','user','hi','t')"
            )
            cnt = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert cnt == 1


class TestSafeRemove:
    """safe_remove: 存在才删，不存在静默跳过。"""

    def test_removes_existing_file(self, tmp_path):
        f = tmp_path / "x.db"
        f.write_text("data")
        safe_remove(f)
        assert not f.exists()

    def test_missing_file_no_error(self, tmp_path):
        """文件不存在时不抛异常（即 os.path.exists 检查生效）。"""
        missing = tmp_path / "nope.db"
        # 不应抛 FileNotFoundError
        safe_remove(missing)
        assert not missing.exists()
