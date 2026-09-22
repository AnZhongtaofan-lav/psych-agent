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

import logging
import re
import sys
import tempfile
from pathlib import Path

import pytest

# ---- 路径引导：项目根目录 = tests/ 的上一级 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 日志路径脱敏（必须在 import app.* 之前安装）
# ------------------------------------------------------------
# 背景：pytest-html 会把 pytest 捕获的 stdout（含 app 日志）原样写入
# reports/test-report.html。database.py 的日志形如
#   数据库初始化完成: path=C:\Users\CCC\AppData\Local\Temp\pytest-x\test.db
# 会把 Windows 用户名与本机 Temp 路径永久写进公开仓库的报告。
#
# 方案：在测试环境给每个 app logger 的 handler 挂一个过滤器，
# 把日志记录中的本机绝对路径统一替换为占位符（生产环境不受影响，
# 运维日志仍保留真实路径）。同时用正则兜底，即使换机器/换用户生成
# 报告，用户名也不会泄漏。
# ============================================================


class _PathRedactingFilter(logging.Filter):
    r"""日志记录路径脱敏过滤器（仅测试环境启用）。

    脱敏规则（先精确前缀替换，再正则兜底）：
        <系统临时目录>\...   → <TEMP>\...
        <用户主目录>\...     → <HOME>\...
        <项目根目录>\...     → <PROJECT_ROOT>\...
        X:\Users\<名>\...    → <HOME>\...       （正则兜底，Windows）
        /home/<名>/... 等    → <HOME>/...       （正则兜底，类 Unix）
        pytest-of-<名>\...  → pytest-of-<USER>  （pytest 临时目录名兜底）
    """

    # Windows 下盘符/路径大小写不敏感（如 c:\ 与 C:\ 等价）
    _FLAGS = re.IGNORECASE if sys.platform.startswith("win") else 0

    def __init__(self) -> None:
        super().__init__()
        # 精确前缀映射：路径前缀 → 占位符（替换时按长度降序，先长后短，
        # 保证 Temp（位于 Home 之下）优先于 Home 命中）
        prefixes = [
            (Path(tempfile.gettempdir()), "<TEMP>"),
            (Path.home(), "<HOME>"),
            (PROJECT_ROOT, "<PROJECT_ROOT>"),
        ]
        prefixes.sort(key=lambda item: len(str(item[0])), reverse=True)
        self._prefix_rules: list[tuple[re.Pattern[str], str]] = [
            (
                re.compile(
                    re.escape(str(root)).replace(r"\:", ":") + r"[\\/]?",
                    self._FLAGS,
                ),
                placeholder,
            )
            for root, placeholder in prefixes
        ]
        # 正则兜底：
        # 1. 任何 X:\Users\<用户名> 形态（捕获本机用户名）
        # 2. pytest 临时工厂目录 basename 为 pytest-of-<系统用户名>，
        #    即使 Temp 前缀被替换，尾部仍会泄漏用户名（pytest-of-CCC）
        self._fallback_rules: tuple[tuple[re.Pattern[str], str], ...] = (
            (re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+", self._FLAGS), "<HOME>"),
            (re.compile(r"(?<![A-Za-z0-9])/(?:home|Users)/[^/\s]+"), "<HOME>"),
            (re.compile(r"pytest-of-[^\\/\s\"']+"), "pytest-of-<USER>"),
        )

    def redact(self, text: str) -> str:
        """对单行文本执行路径脱敏。"""
        for pattern, placeholder in self._prefix_rules:
            text = pattern.sub(placeholder, text)
        for pattern, placeholder in self._fallback_rules:
            text = pattern.sub(placeholder, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # 先插值（惰性 %s 参数在此时展开），再整体脱敏；
        # 处理后把 args 置空，避免 Formatter 二次插值
        message = record.getMessage()
        record.msg = self.redact(message)
        record.args = ()
        return True


# 单例过滤器，所有 logger 共用
_path_filter = _PathRedactingFilter()


def _attach_filter(logger_obj: logging.Logger) -> logging.Logger:
    """给一个 logger 及其全部 handler 挂上路径脱敏过滤器（幂等）。"""
    logger_obj.addFilter(_path_filter)
    for handler in logger_obj.handlers:
        handler.addFilter(_path_filter)
    return logger_obj


# 必须在 `from app.main import create_app` 之前补丁：
# app 各模块在 import 时即调用 get_logger(__name__)
import app.common.logger as _logger_module  # noqa: E402

_original_get_logger = _logger_module.get_logger


def _get_logger_redacted(name: str) -> logging.Logger:
    """get_logger 包装：创建 logger 后自动挂载路径脱敏过滤器。"""
    return _attach_filter(_original_get_logger(name))


_logger_module.get_logger = _get_logger_redacted

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.storage.database import Database, safe_remove  # noqa: E402

# 防御性兜底：若补丁前已有 app.* logger 被创建，统一补挂过滤器
for _existing in list(logging.Logger.manager.loggerDict.values()):
    if isinstance(_existing, logging.Logger) and _existing.name.startswith("app"):
        _attach_filter(_existing)
del _existing


# ============================================================
# pytest-metadata 环境元数据路径脱敏
# ------------------------------------------------------------
# 背景：pytest-html 的 environment 段由 pytest-metadata 插件填充，
# 它会自动采集进程环境变量，把 "JAVA_HOME": "D:\高性能框架\JDK"
# 这类本机绝对路径写入公开报告。日志过滤器无法覆盖该通道，
# 因此在 pytest 配置阶段直接清理 config._metadata。
# ============================================================

# 绝对路径检测：Windows 盘符路径（D:\...、D:/...）或类 Unix 绝对路径
_ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|(?<![A-Za-z0-9])/(?:home|Users|mnt|tmp|var)/)"
)

_METADATA_REDACTED = "<REDACTED>"


def _scrub_metadata_value(value):  # noqa: ANN202
    """递归清理 metadata 值：含本机绝对路径的字符串一律替换。

    - str：命中绝对路径模式 → 占位符，否则原样返回
    - dict：逐键递归（保留键名，便于看出"有哪些环境项"）
    - list/tuple：逐元素递归
    - 其他类型（版本号等）：原样返回
    """
    if isinstance(value, str):
        return _METADATA_REDACTED if _ABSOLUTE_PATH_RE.search(value) else value
    if isinstance(value, dict):
        return {k: _scrub_metadata_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_metadata_value(v) for v in value]
    return value


def pytest_metadata(metadata, config):  # noqa: ANN001
    """pytest-metadata 官方扩展 hook：元数据采集【全部完成后】回调。

    实现要点（已核对 pytest_metadata/plugin.py 源码）：
        - 新版插件把数据存在 config.stash[metadata_key]，而非旧版的
          config._metadata，因此直接改 config._metadata 无效；
        - 插件在 pytest_configure 末尾调用
          config.hook.pytest_metadata(metadata=..., config=...)，
          此时 JAVA_HOME 等环境变量项已写入，是最稳妥的脱敏注入点；
        - 直接原地修改传入的 metadata 字典即可，pytest-html 随后读取
          的就是脱敏结果。
    """
    if isinstance(metadata, dict):
        metadata.update(_scrub_metadata_value(metadata))


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

