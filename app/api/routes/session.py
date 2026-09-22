# -*- coding: utf-8 -*-
"""
会话路由：创建与结束。

安全说明：
- 会话 ID 与匿名 ID 均为服务端生成/校验的 UUID，无身份语义
- 创建会话即返回热线号码：任何一轮对话开始前，
  客户端就已经持有心理援助热线（安全兜底前移）
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.api.dependencies import Services, provide_services
from app.api.schemas.chat_schemas import SessionEndResponse
from app.api.schemas.session_schemas import SessionCreateRequest, SessionResponse
from app.common.constants import SessionState
from app.common.exceptions import SessionNotFoundError

router = APIRouter(tags=["session"])


@router.post("/session", response_model=SessionResponse)
def create_session(
    payload: SessionCreateRequest | None = None,
    services: Services = Depends(provide_services),
) -> SessionResponse:
    """创建会话。anonymous_id 缺省时由服务端生成（推荐）。"""
    # 请求体可整体省略：无 body 时按默认创建
    anonymous_id = (
        payload.anonymous_id
        if payload is not None and payload.anonymous_id
        else str(uuid.uuid4())
    )
    session = services.sessions.create(anonymous_id=anonymous_id)
    return SessionResponse(
        session_id=session.session_id,
        anonymous_id=session.anonymous_id,
        persona_type=session.persona_type,  # type: ignore[arg-type] —— 受控值
        crisis_hotline=services.interceptor.hotline_primary,
        created_at=session.created_at,
    )


@router.post("/session/{session_id}/end", response_model=SessionEndResponse)
def end_session(
    session_id: str,
    services: Services = Depends(provide_services),
) -> SessionEndResponse:
    """结束会话（用户主动）。已终止会话重复结束 → 404。"""
    session = services.sessions.get(session_id)
    if session is None or session.state not in (
        SessionState.ACTIVE.value,
        SessionState.CRISIS_WATCH.value,
    ):
        raise SessionNotFoundError()
    services.sessions.update_after_round(
        session_id, state=SessionState.ENDED.value
    )
    return SessionEndResponse(session_id=session_id, state=SessionState.ENDED)
