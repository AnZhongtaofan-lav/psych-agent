# -*- coding: utf-8 -*-
"""
FastAPI 应用入口 —— 三层架构的最终装配点。

装配顺序（依赖单向：交互层 → 逻辑层 → 数据层）：
    Database（数据层）
      → AuditLogger / Repositories
    LlmClient（可插拔：未配置 Key 时全链路纯规则运行）
      → RiskEngine / EmotionEngine / ReplyGenerator
    CrisisInterceptor → DialogueStrategy
      → Services 容器 → 路由

启动方式：
    uvicorn app.main:app --reload
    或安装后执行 psych-server（见 pyproject [project.scripts]）
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import Services
from app.api.middleware.anonymize_log import AccessLogMiddleware
from app.api.middleware.input_guard import PayloadSizeLimitMiddleware
from app.api.routes import chat, media, profile, session
from app.common.config import settings
from app.common.exceptions import AppException
from app.common.logger import get_logger
from app.core.dialogue.reply_generator import ReplyGenerator
from app.core.dialogue.strategy import DialogueStrategy
from app.core.emotion.emotion_engine import EmotionEngine
from app.core.llm.client import LlmClient
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

logger = get_logger(__name__)


def build_services(db: Database) -> Services:
    """装配服务容器（依赖注入集中点，便于测试替身替换）。

    LLM 装配原则（可插拔语义）：
        未配置 LLM_API_KEY/LLM_BASE_URL → 三个引擎的 llm 函数句柄
        传 None → 引擎内部走纯规则分支。高危拦截不受影响。
    """
    audit = AuditLogger(db)
    llm = LlmClient()
    # 拦截器单例：热线配置只有一份来源（路由响应与拦截话术一致）
    interceptor = CrisisInterceptor(
        hotline_primary=settings.crisis_hotline_primary,
        hotline_secondary=settings.crisis_hotline_secondary,
        emergency_number=settings.emergency_number,
    )

    return Services(
        db=db,
        audit=audit,
        sessions=SessionRepository(db),
        messages=MessageRepository(db, audit),
        risk_events=RiskEventRepository(db),
        profiles=ProfileRepository(db),
        risk_engine=RiskEngine(llm_level_fn=llm.as_level_fn() if llm.is_available else None),
        emotion_engine=EmotionEngine(llm_emotion_fn=llm.as_emotion_fn() if llm.is_available else None),
        interceptor=interceptor,
        strategy=DialogueStrategy(
            interceptor=interceptor,
            reply_generator=ReplyGenerator(
                llm_fn=llm.as_complete_fn() if llm.is_available else None
            ),
        ),
        llm_enabled=llm.is_available,
    )


def create_app(db: Database | None = None) -> FastAPI:
    """应用工厂（测试可注入独立 Database 实现隔离）。"""
    # 数据层：默认按配置路径；测试注入临时库
    database = db if db is not None else Database(settings.db_path)
    database.init()  # 幂等建表（fail-fast：词典等资源校验也在 import 期完成）
    services = build_services(database)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        media.ensure_media_dirs()
        logger.info(
            "AI 心理服务智能体启动: llm_enabled=%s, hotline=%s, media_dir=%s",
            services.llm_enabled,
            "已配置",  # 热线号码不落日志（号码本身非 PII，但保持日志最小化习惯）
            settings.media_dir,
        )
        yield
        logger.info("AI 心理服务智能体关闭")

    app = FastAPI(
        title="AI 心理服务智能体",
        description="三层架构：交互层 / 逻辑层 / 数据层。含四级风险分级、L3 高危拦截与全链路 PII 脱敏。",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 服务容器挂载（路由经 provide_services 取用）
    app.state.services = services

    # 中间件（顺序：先加的在外层；两个都是无状态横切设施）
    app.add_middleware(PayloadSizeLimitMiddleware)
    app.add_middleware(AccessLogMiddleware)

    # CORS 中间件：允许静态页面在任意来源下调用 API（本地开发 / file:// 直开场景）。
    # 注意：CORS 不是鉴权机制；生产部署若收紧来源，改 allow_origins 为白名单即可。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # 路由
    app.include_router(session.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(media.router, prefix="/api")

    # ---- 前端静态资源：挂载整个 static/ 目录 ----
    _STATIC_DIR = Path(__file__).resolve().parent / "static"
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR)), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """SPA 入口页（浏览器访问 http://127.0.0.1:8000/ 直接使用）。"""
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")

    # ---- 健康检查 ----
    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        """探活 + LLM 配置状态（不暴露任何内部细节）。"""
        return {"status": "ok", "llm_enabled": services.llm_enabled}

    # ---- 全局异常处理 ----
    @app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
        """业务异常 → 安全文案（不含内部细节）。"""
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        """未预期异常 → 500 通用文案；堆栈只进日志（日志无用户原文）。

        注意：不向客户端回显 exc —— 防止内部信息（路径/SQL/类名）泄露。
        """
        logger.error("未处理异常: %s: %s", type(exc).__name__, exc)
        return JSONResponse(status_code=500, content={"detail": "服务内部错误，请稍后重试"})

    return app


def run() -> None:
    """psych-server 命令行入口。"""
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


# 模块级应用实例：uvicorn app.main:app 直接使用
app = create_app()
