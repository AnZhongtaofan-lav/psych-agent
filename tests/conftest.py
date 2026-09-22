# -*- coding: utf-8 -*-
"""
pytest 全局 fixture 与路径配置。

关键职责：
1. 将项目根目录加入 sys.path，保证 `import app.xxx` 在任何工作目录下可用
2. 提供临时 SQLite 数据库 fixture（每个测试函数独立、互不污染）
3. 提供 FastAPI TestClient fixture（应用工厂注入临时库，天然隔离）

数据库清理策略（双保险，二选一即可生效）：
    A. 推荐：Database.reset() —— drop_all + create_all，不碰文件系统，
       规避 Windows 下 WAL/SHM 句柄占用导致 os.remove 失败的问题。
    B. 兜底：os.remove（带 os.path.exists 检查）—— 显式删除临时库文件
       及其 WAL/SHM 伴生文件，保证 tmp_path 彻底干净。
两种方式都不会去碰生产库 data/psych.db。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---- 路径引导：项目根目录 = tests/ 的上一级 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.storage.database import Database, safe_remove  # noqa: E402


@pytest.fixture()
def test_db(tmp_path):
    """每个测试函数独立的临时 SQLite 数据库。

    清理采用双层策略：
      - 测试内部若需重置数据，调用 db.reset()（drop_all + init）
      - fixture 结束时兜底删除 .db / .db-wal / .db-shm（带存在性检查）
    两种方式都不会去碰生产库 data/psych.db。
    """
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    yield db
    # 兜底清理：存在才删，规避 Windows 句柄占用异常
    safe_remove(db_path)
    safe_remove(tmp_path / "test.db-wal")
    safe_remove(tmp_path / "test.db-shm")


@pytest.fixture()
def client(test_db):
    """注入临时库的 TestClient（纯规则模式：测试环境无 LLM 配置）。"""
    app = create_app(db=test_db)
    with TestClient(app) as c:
        # 暴露 db 供测试直接查库断言（如脱敏落库验证）
        c.db = test_db  # type: ignore[attr-defined]
        yield c


@pytest.fixture()
def session_id(client):
    """预创建的会话 ID。"""
    resp = client.post("/api/session")
    assert resp.status_code == 200
    return resp.json()["session_id"]

