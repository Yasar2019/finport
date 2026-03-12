"""Alembic env.py — async-compatible migration environment."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Pull in all ORM models so autogenerate sees them
from app.database.session import Base  # noqa: F401
import app.models  # noqa: F401 — triggers all model registrations

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Config keys
_SQLALCHEMY_URL = "sqlalchemy.url"


def _sync_url(url: str) -> str:
    """Convert asyncpg URL to psycopg2 for Alembic's synchronous env."""
    return url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    import os
    db_url = os.getenv("DATABASE_URL") or config.get_main_option(_SQLALCHEMY_URL)
    if not db_url:
        raise ValueError("DATABASE_URL not set and sqlalchemy.url not configured in alembic.ini")
    url = _sync_url(db_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    import os

    db_url = os.getenv("DATABASE_URL") or config.get_main_option(_SQLALCHEMY_URL)
    if not db_url:
        raise ValueError("DATABASE_URL not set and sqlalchemy.url not configured in alembic.ini")
    sync_url = _sync_url(db_url)

    connectable = engine_from_config(
        {"sqlalchemy.url": sync_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
