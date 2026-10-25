"""Функции доступа к данным. Все принимают открытую AsyncSession; транзакциями управляет вызывающий."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from skazki_bot.db.models import Child, GenerationRun, Tale, User

_LAST_SEEN_REFRESH = timedelta(hours=1)


# --- Пользователи -------------------------------------------------------------------------------
async def upsert_user(session: AsyncSession, tg_id: int) -> User:
    now = datetime.now(UTC)
    user = await session.get(User, tg_id)
    if user is None:
        user = User(id=tg_id, created_at=now, last_seen_at=now)
        session.add(user)
    elif now - user.last_seen_at > _LAST_SEEN_REFRESH:
        user.last_seen_at = now
    await session.flush()
    return user


async def set_tale_length(session: AsyncSession, user_id: int, length: str) -> None:
    await session.execute(update(User).where(User.id == user_id).values(tale_length=length))


async def delete_user_data(session: AsyncSession, user_id: int) -> None:
    """Полное удаление: сказки, профили детей и самого пользователя."""
    await session.execute(delete(GenerationRun).where(GenerationRun.user_id == user_id))
    await session.execute(delete(Tale).where(Tale.user_id == user_id))
    await session.execute(delete(Child).where(Child.user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))


# --- Luna's warm words (cheer skill) -------------------------------------------------------------
@dataclass(frozen=True)
class CheerCandidate:
    user_id: int
    freq: str
    last_at: datetime | None


async def set_cheer_freq(session: AsyncSession, user_id: int, freq: str) -> None:
    """Choosing a frequency (including «off») also means the invitation was answered."""
    await session.execute(
        update(User).where(User.id == user_id).values(cheer_freq=freq, cheer_asked=True)
    )


async def mark_cheer_asked(session: AsyncSession, user_id: int) -> bool:
    """True only for the call that flips the flag: the invitation is shown exactly once."""
    result = await session.execute(
        update(User).where(User.id == user_id, User.cheer_asked.is_(False)).values(cheer_asked=True)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def list_cheer_candidates(session: AsyncSession) -> list[CheerCandidate]:
    rows = await session.execute(
        select(User.id, User.cheer_freq, User.cheer_last_at)
        .where(User.cheer_freq != "off")
        .order_by(User.id)
    )
    return [CheerCandidate(user_id=r[0], freq=r[1], last_at=r[2]) for r in rows]


async def claim_cheer_slot(
    session: AsyncSession, user_id: int, *, now: datetime, cutoff: datetime
) -> bool:
    """Atomically take the next slot: succeeds for exactly one caller even across replicas."""
    result = await session.execute(
        update(User)
        .where(
            User.id == user_id,
            User.cheer_freq != "off",
            or_(User.cheer_last_at.is_(None), User.cheer_last_at <= cutoff),
        )
        .values(cheer_last_at=now)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def cheer_context(session: AsyncSession, user_id: int) -> tuple[str | None, list[str]]:
    """The active child's name (first profile as a fallback) and the recently sent item ids."""
    name = await session.scalar(
        select(Child.name)
        .where(Child.user_id == user_id)
        .order_by(Child.is_active.desc(), Child.id)
        .limit(1)
    )
    user = await session.get(User, user_id)
    return name, list((user.cheer_recent if user else None) or [])


async def push_cheer_sent(
    session: AsyncSession, user_id: int, item_id: str, *, limit: int, now: datetime
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        return
    user.cheer_recent = [*(user.cheer_recent or []), item_id][-limit:]  # new list -> JSON change
    user.cheer_last_at = now
    await session.flush()


# --- Дети ---------------------------------------------------------------------------------------
async def list_children(session: AsyncSession, user_id: int) -> list[Child]:
    result = await session.scalars(select(Child).where(Child.user_id == user_id).order_by(Child.id))
    return list(result)


async def get_child(session: AsyncSession, user_id: int, child_id: int) -> Child | None:
    return await session.scalar(select(Child).where(Child.id == child_id, Child.user_id == user_id))


async def get_active_child(session: AsyncSession, user_id: int) -> Child | None:
    children = await list_children(session, user_id)
    if not children:
        return None
    for child in children:
        if child.is_active:
            return child
    children[0].is_active = True  # самовосстановление: активного нет — берём первого
    await session.flush()
    return children[0]


async def create_child(
    session: AsyncSession,
    user_id: int,
    *,
    name: str,
    gender: str,
    age: int,
    interests: list[str],
    extra_interests: str,
) -> Child:
    await session.execute(update(Child).where(Child.user_id == user_id).values(is_active=False))
    child = Child(
        user_id=user_id,
        name=name,
        gender=gender,
        age=age,
        interests=list(interests),
        extra_interests=extra_interests,
        is_active=True,
    )
    session.add(child)
    await session.flush()
    return child


async def update_child(
    session: AsyncSession,
    user_id: int,
    child_id: int,
    **fields: object,
) -> Child | None:
    child = await get_child(session, user_id, child_id)
    if child is None:
        return None
    for key, value in fields.items():
        if key == "interests":
            value = list(value)  # type: ignore[call-overload]  # новый список → JSON помечается изменённым
        setattr(child, key, value)
    await session.flush()
    return child


async def set_active_child(session: AsyncSession, user_id: int, child_id: int) -> bool:
    if await get_child(session, user_id, child_id) is None:
        return False
    await session.execute(
        update(Child).where(Child.user_id == user_id).values(is_active=(Child.id == child_id))
    )
    return True


async def delete_child(session: AsyncSession, user_id: int, child_id: int) -> bool:
    child = await get_child(session, user_id, child_id)
    if child is None:
        return False
    await session.execute(delete(Tale).where(Tale.child_id == child_id))
    await session.delete(child)
    await session.flush()
    await get_active_child(session, user_id)  # если удалили активного — назначим другого
    return True


async def count_children(session: AsyncSession, user_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Child).where(Child.user_id == user_id)
        )
        or 0
    )


# --- Сказки -------------------------------------------------------------------------------------
async def add_tale(
    session: AsyncSession,
    *,
    user_id: int,
    child_id: int,
    seed_id: str | None,
    mode: str,
    bedtime: bool,
    title: str,
    text: str,
    skill: str | None = None,
    parent_note: str | None = None,
) -> Tale:
    tale = Tale(
        user_id=user_id,
        child_id=child_id,
        seed_id=seed_id,
        skill=skill,
        parent_note=parent_note,
        mode=mode,
        bedtime=bedtime,
        title=title,
        text=text,
    )
    session.add(tale)
    await session.flush()
    return tale


async def get_tale(session: AsyncSession, user_id: int, tale_id: int) -> Tale | None:
    return await session.scalar(select(Tale).where(Tale.id == tale_id, Tale.user_id == user_id))


async def list_tales(
    session: AsyncSession, user_id: int, child_id: int, *, limit: int, offset: int = 0
) -> list[Tale]:
    result = await session.scalars(
        select(Tale)
        .options(defer(Tale.text))  # в списке тексты не нужны
        .where(Tale.user_id == user_id, Tale.child_id == child_id)
        .order_by(Tale.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def count_tales(session: AsyncSession, user_id: int, child_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Tale)
            .where(Tale.user_id == user_id, Tale.child_id == child_id)
        )
        or 0
    )


async def count_tales_since(session: AsyncSession, user_id: int, since: datetime) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Tale)
            .where(Tale.user_id == user_id, Tale.created_at >= since)
        )
        or 0
    )


async def set_rating(session: AsyncSession, user_id: int, tale_id: int, rating: int) -> bool:
    result = await session.execute(
        update(Tale).where(Tale.id == tale_id, Tale.user_id == user_id).values(rating=rating)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


@dataclass
class TaleStats:
    """Сводка по истории ребёнка — вход для подбора классического сюжета."""

    seen: Counter[str] = field(default_factory=Counter)
    liked: set[str] = field(default_factory=set)
    disliked: set[str] = field(default_factory=set)


async def tale_stats(session: AsyncSession, child_id: int) -> TaleStats:
    stats = TaleStats()
    rows = await session.execute(
        select(Tale.seed_id, Tale.rating).where(
            Tale.child_id == child_id, Tale.seed_id.is_not(None)
        )
    )
    for seed_id, rating in rows:
        if seed_id is None:
            continue
        stats.seen[seed_id] += 1
        if rating > 0:
            stats.liked.add(seed_id)
        elif rating < 0:
            stats.disliked.add(seed_id)
    return stats


# --- Память харнесса и трассы ---------------------------------------------------------------------
async def recent_tales(session: AsyncSession, child_id: int, *, limit: int = 5) -> list[Tale]:
    """Последние сказки ребёнка (с текстом) — «память» для сиквелов и разнообразия форматов."""
    result = await session.scalars(
        select(Tale).where(Tale.child_id == child_id).order_by(Tale.id.desc()).limit(limit)
    )
    return list(result)


async def add_run(session: AsyncSession, **fields: object) -> GenerationRun:
    run = GenerationRun(**fields)
    session.add(run)
    await session.flush()
    return run


@dataclass(frozen=True)
class SkillUsage:
    skill: str
    runs: int
    ok: int
    blocked: int
    errors: int
    revised: int
    avg_latency_ms: int
    avg_input_tokens: int
    avg_output_tokens: int


async def skill_usage_stats(session: AsyncSession, since: datetime) -> list[SkillUsage]:
    """Сводка по форматам для админ-команды /stats."""
    run = GenerationRun
    # Агрегируем в Python: переносимо между SQLite и PostgreSQL, объёмы небольшие
    items = await session.scalars(select(run).where(run.created_at >= since))
    buckets: dict[str, list[GenerationRun]] = {}
    for item in items:
        buckets.setdefault(item.skill or "auto", []).append(item)
    stats = []
    for name, group in sorted(buckets.items()):
        n = len(group)
        stats.append(
            SkillUsage(
                skill=name,
                runs=n,
                ok=sum(r.outcome == "ok" for r in group),
                blocked=sum(r.outcome == "blocked" for r in group),
                errors=sum(r.outcome == "error" for r in group),
                revised=sum(r.revised for r in group),
                avg_latency_ms=sum(r.latency_ms for r in group) // n,
                avg_input_tokens=sum(r.input_tokens for r in group) // n,
                avg_output_tokens=sum(r.output_tokens for r in group) // n,
            )
        )
    return stats
