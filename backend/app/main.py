"""
FinPort Backend Application
Entry point for the FastAPI application.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.database.session import create_db_and_tables
from app.core.events import startup_event, shutdown_event

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: runs startup tasks, yields, runs shutdown tasks."""
    await startup_event()
    yield
    await shutdown_event()


def create_application() -> FastAPI:
    application = FastAPI(
        title="FinPort API",
        description="Financial Portfolio Intelligence Platform",
        version="0.1.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # Security: restrict allowed hosts in production
    if not settings.DEBUG:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix=settings.API_V1_STR)

    return application


app = create_application()


@app.get("/health", tags=["Infrastructure"])
async def health_check():
    """Basic liveness probe."""
    return {"status": "ok", "service": "finport-api"}


@app.get("/readiness", tags=["Infrastructure"])
async def readiness_check():
    """Readiness probe: checks DB connectivity."""
    from app.database.session import check_db_connection

    db_ok = await check_db_connection()
    status = "ready" if db_ok else "not_ready"
    return {"status": status, "database": "connected" if db_ok else "disconnected"}
