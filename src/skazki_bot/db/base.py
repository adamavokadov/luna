from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]


def ensure_sqlite_dir(url: str) -> None:
    """Для файловой SQLite создаёт каталог под базу (например, ./data)."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(str(parsed.database)).parent.mkdir(parents=True, exist_ok=True)


def create_engine(url: str) -> AsyncEngine:
    ensure_sqlite_dir(url)
    is_sqlite = make_url(url).get_backend_name() == "sqlite"

    engine = create_async_engine(url, pool_pre_ping=True)

    if is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    # expire_on_commit=False: объекты остаются читаемыми после закрытия сессии
    return async_sessionmaker(engine, expire_on_commit=False)
