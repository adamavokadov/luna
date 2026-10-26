"""ORM-модели. Минимизация данных: храним только Telegram id родителя и профиль ребёнка."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    false,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UTCDateTime(TypeDecorator[datetime]):
    """Всегда timezone-aware UTC, независимо от СУБД (SQLite хранит «наивные» значения)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Ожидается datetime с tzinfo")
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        moment: datetime = value
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """Родитель (пользователь Telegram). Имя и username намеренно не сохраняем."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    tale_length: Mapped[str] = mapped_column(String(10), default="normal")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    # Luna's warm words (cheer skill). Off by default: a proactive message needs consent.
    cheer_freq: Mapped[str] = mapped_column(String(8), default="off", server_default="off")
    cheer_asked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    cheer_last_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    cheer_recent: Mapped[list[str] | None] = mapped_column(JSON, default=None)  # last item ids

    children: Mapped[list[Child]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Child(Base):
    __tablename__ = "children"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(40))
    gender: Mapped[str] = mapped_column(String(5))
    age: Mapped[int] = mapped_column(SmallInteger)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)  # ключи из каталога
    extra_interests: Mapped[str] = mapped_column(String(300), default="")  # свободный текст
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    user: Mapped[User] = relationship(back_populates="children")


class Tale(Base):
    __tablename__ = "tales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    child_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("children.id", ondelete="CASCADE"), index=True
    )
    seed_id: Mapped[str | None] = mapped_column(String(64), default=None)  # id классического сюжета
    skill: Mapped[str | None] = mapped_column(String(40), default=None)  # формат (навык)
    parent_note: Mapped[str | None] = mapped_column(Text, default=None)  # «Для родителей»
    mode: Mapped[str] = mapped_column(String(16))
    bedtime: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(SmallInteger, default=0)  # -1 / 0 / +1
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, index=True)


class GenerationRun(Base):
    """Трасса одного запуска харнесса: для стоимости, отладки и качества. Текстов и имён здесь нет."""

    __tablename__ = "generation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tale_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tales.id", ondelete="SET NULL"), default=None, index=True
    )
    skill: Mapped[str | None] = mapped_column(String(40), default=None)
    model: Mapped[str] = mapped_column(String(80), default="")
    outcome: Mapped[str] = mapped_column(String(16), default="ok")  # ok | blocked | refused | error
    steps: Mapped[int] = mapped_column(SmallInteger, default=0)
    tool_calls: Mapped[list[str]] = mapped_column(JSON, default=list)
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)  # коды замечаний guard-слоя
    revised: Mapped[bool] = mapped_column(Boolean, default=False)
    critic_used: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, index=True)
