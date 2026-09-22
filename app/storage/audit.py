# -*- coding: utf-8 -*-
"""
脱敏审计模块。

职责：把 anonymizer 报告的脱敏动作写入 audit_log 表。
安全红线：
    1. 只记录动作类型与发生位置，【绝不记录原文或掩码文本】
    2. 审计失败不阻断主流程（降级为日志告警）——审计是"增强可信度"，
       不能成为可用性单点；真正的脱敏由调用方在写库前已完成
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.common.logger import get_logger
from app.storage.anonymizer import AnonymizeReport
from app.storage.database import Database

logger = get_logger(__name__)


def _now_iso() -> str:
    """统一时间戳：UTC ISO 8601（避免时区歧义）。"""
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """脱敏审计写入器。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def record(self, report: AnonymizeReport, context: str) -> None:
        """将一次脱敏报告写入审计表（每个动作一行）。

        参数:
            report: anonymize() 返回的脱敏报告（只含动作类型）
            context: 发生位置，取值约定：
                - "entry_middleware"  交互层入口中间件
                - "repository_write"  数据层写入前
        """
        if not report.has_changes:
            return  # 未发生脱敏，无需审计
        try:
            with self._db.connect() as conn:
                for action in report.actions:
                    conn.execute(
                        "INSERT INTO audit_log (audit_id, action, context, details, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), action, context, "{}", _now_iso()),
                    )
        except Exception:  # noqa: BLE001 —— 审计失败必须不阻断主流程
            # 注意：日志里只输出动作类型（report 本身不含原文），安全
            logger.warning("脱敏审计写入失败（已降级）: actions=%s", report.actions)
