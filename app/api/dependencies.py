# -*- coding: utf-8 -*-
"""
服务装配容器 —— 依赖注入的集中点。

职责：
1. 声明交互层依赖的全部服务对象（类型化，便于测试替身替换）
2. provide_services()：路由层获取容器的统一入口

装配关系（main.create_app 中完成）：
    Database → AuditLogger → 各 Repository
    LlmClient(可插拔) → RiskEngine / EmotionEngine / ReplyGenerator
    CrisisInterceptor → DialogueStrategy
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import Request

from app.core.dialogue.strategy import DialogueStrategy
from app.core.emotion.emotion_engine import EmotionEngine
from app.core.risk.interceptors import CrisisInterceptor
from app.core.risk.risk_engine import RiskEngine
from app.storage.audit import AuditLogger
from app.storage.database import Database
from app.storage.repositories import (
    MessageRepository,
    ProfileRepository,
    RiskEventRepository,
    SessionRepository,
)


@dataclass
class Services:
    """应用服务容器（一个 FastAPI 实例一份）。"""

    # 数据层
    db: Database
    audit: AuditLogger
    sessions: SessionRepository
    messages: MessageRepository
    risk_events: RiskEventRepository
    profiles: ProfileRepository

    # 逻辑层
    risk_engine: RiskEngine
    emotion_engine: EmotionEngine
    interceptor: CrisisInterceptor
    strategy: DialogueStrategy

    # 运行时标记
    llm_enabled: bool


def provide_services(request: Request) -> Services:
    """路由层统一取容器入口（request.app.state 注入）。"""
    return request.app.state.services  # type: ignore[no-any-return]
