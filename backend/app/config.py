"""
Application configuration via pydantic-settings.
All secrets come from environment variables or the .env file — never hardcoded.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── API ──────────────────────────────────────────────────────────────────
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # ── Security ─────────────────────────────────────────────────────────────
    # Single-user bearer token for Phase 1 (local use)
    API_SECRET_KEY: str = Field(..., min_length=32)
    # Fernet key for encrypting files at rest (base64-encoded 32-byte key)
    STORAGE_ENCRYPTION_KEY: str = Field(..., min_length=44)
    # JWT settings (Phase 2+)
    JWT_SECRET_KEY: str = Field(default="", description="Required in Phase 2+")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://finport:finport@localhost:5432/finport"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Redis / Celery ───────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── File Storage ─────────────────────────────────────────────────────────
    STORAGE_BACKEND: str = "local"  # local | s3
    LOCAL_STORAGE_ROOT: str = "./data/uploads"
    RAW_TEXT_STORAGE_ROOT: str = "./data/raw_text"
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_MIME_TYPES: list[str] = [
        "application/pdf",
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",  # some Excel files
    ]

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    # ── Reconciliation ───────────────────────────────────────────────────────
    RECONCILIATION_AUTO_RESOLVE_CONFIDENCE: float = 0.95
    DUPLICATE_DETECTION_DATE_WINDOW_DAYS: int = 3

    # ── Single-user ID (Phase 1) ─────────────────────────────────────────────
    # In Phase 1 there is one user; this constant acts as the user_id
    # When multi-tenancy is added, replace with real auth.
    SINGLE_USER_ID: str = "00000000-0000-0000-0000-000000000001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
