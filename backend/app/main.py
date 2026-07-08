"""Beeline backend application entrypoint."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import admin, chat, metadata, workspace
from app.core.config import get_settings
from app.core.database import init_db
from app.core.exceptions import BeelineError
from app.core.logging import configure_logging, get_logger
from app.services.metadata_sync import scheduled_sync_loop

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    await init_db()
    logger.info("Beeline backend started (%s)", settings.get("app.environment"))
    sync_task = None
    if settings.get("metadata_sync.enabled", True):
        sync_task = asyncio.create_task(scheduled_sync_loop())
    yield
    if sync_task:
        sync_task.cancel()
    from app.connectors.registry import close_all
    await close_all()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Beeline API",
        description="Enterprise NL-to-SQL Analytics & Metadata Platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get("app.cors_origins", ["http://localhost:4200"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(BeelineError)
    async def beeline_error_handler(request: Request, exc: BeelineError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    prefix = settings.get("app.api_prefix", "/api/v1")
    app.include_router(chat.router, prefix=prefix)
    app.include_router(metadata.router, prefix=prefix)
    app.include_router(metadata.glossary_router, prefix=prefix)
    app.include_router(workspace.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(admin.health_router, prefix=prefix)
    return app


app = create_app()
