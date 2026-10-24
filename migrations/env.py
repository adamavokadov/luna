"""Alembic в async-режиме. URL базы берётся из DATABASE_URL (см. skazki_bot.config)."""

from __future__ import annotations

import asyncio
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from skazki_bot.config import get_database_url
from skazki_bot.db.base import ensure_sqlite_dir
from skazki_bot.db.models import Base, UTCDateTime

config = context.config
target_metadata = Base.metadata
DATABASE_URL = get_database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")
ensure_sqlite_dir(DATABASE_URL)


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    # TypeDecorator в миграциях заменяем на обычный тип — миграции не должны зависеть от кода
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        render_as_batch=IS_SQLITE,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=render_item,
        render_as_batch=IS_SQLITE,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
