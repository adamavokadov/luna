"""Оркестрация создания сказки: лимиты → вход харнесса → запуск → сохранение сказки и трассы."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import User
from skazki_bot.domain.enums import Gender, TaleLength
from skazki_bot.harness import (
    ChildSnapshot,
    GuardBlocked,
    HarnessError,
    RecentTale,
    RunInput,
    RunRequest,
    RunResult,
    RunTrace,
    TaleHarness,
)
from skazki_bot.harness.runner import ProgressCallback
from skazki_bot.harness.skills import BEDTIME
from skazki_bot.llm.base import LLMError
from skazki_bot.logging import get_logger

log = get_logger(__name__)

EXCERPT_CHARS = 350
RECENT_LIMIT = 5


class DailyLimitReached(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"daily limit {limit}")
        self.limit = limit


class AlreadyGenerating(Exception):
    """Для этого пользователя сказка уже сочиняется."""


class ChildNotFound(Exception):
    pass


@dataclass(frozen=True)
class TaleRequest:
    skill: str | None = None  # формат (навык); None — выберет модель
    bedtime: bool = False  # наложение «сказка на ночь»
    classic_id: str | None = None
    idea: str | None = None


@dataclass(frozen=True)
class GeneratedTale:
    id: int
    title: str
    text: str
    parent_note: str | None
    skill: str | None


class TaleService:
    def __init__(self, *, sf: SessionFactory, harness: TaleHarness, settings: Settings) -> None:
        self._sf = sf
        self._harness = harness
        self._settings = settings
        self._active: set[int] = set()  # при нескольких репликах бота заменить на Redis-блокировку

    # --- Лимиты -----------------------------------------------------------------------------
    def _is_admin(self, user_id: int) -> bool:
        return user_id in self._settings.admin_ids

    def _day_start_utc(self, now: datetime | None = None) -> datetime:
        tz = ZoneInfo(self._settings.timezone)
        local = (now or datetime.now(UTC)).astimezone(tz)
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    async def remaining_today(self, user_id: int) -> int | None:
        """Сколько сказок ещё доступно сегодня; None — без ограничений."""
        if self._is_admin(user_id):
            return None
        async with self._sf() as session:
            used = await repo.count_tales_since(session, user_id, self._day_start_utc())
        return max(self._settings.daily_tale_limit - used, 0)

    # --- Генерация --------------------------------------------------------------------------
    async def generate(
        self,
        *,
        user_id: int,
        child_id: int,
        request: TaleRequest,
        on_progress: ProgressCallback | None = None,
    ) -> GeneratedTale:
        if user_id in self._active:
            raise AlreadyGenerating
        self._active.add(user_id)  # между проверкой и добавлением нет await → гонки нет
        try:
            return await self._generate(user_id, child_id, request, on_progress)
        finally:
            self._active.discard(user_id)

    async def _generate(
        self,
        user_id: int,
        child_id: int,
        request: TaleRequest,
        on_progress: ProgressCallback | None,
    ) -> GeneratedTale:
        # 1. Короткая транзакция на чтение — соединение не держим, пока идёт генерация
        async with self._sf() as session:
            child = await repo.get_child(session, user_id, child_id)
            if child is None:
                raise ChildNotFound
            user = await session.get(User, user_id)
            stats = await repo.tale_stats(session, child_id)
            recent_rows = await repo.recent_tales(session, child_id, limit=RECENT_LIMIT)
            used = await repo.count_tales_since(session, user_id, self._day_start_utc())

        limit = self._settings.daily_tale_limit
        if not self._is_admin(user_id) and used >= limit:
            raise DailyLimitReached(limit)

        run_input = RunInput(
            child=ChildSnapshot(
                name=child.name,
                gender=Gender(child.gender),
                age=child.age,
                interests=tuple(child.interests),
                extra=child.extra_interests,
            ),
            request=RunRequest(
                skill=request.skill,
                bedtime=request.bedtime,
                classic_id=request.classic_id,
                idea=request.idea,
            ),
            length=_parse_length(user.tale_length if user else None),
            seen=Counter(stats.seen),
            liked=frozenset(stats.liked),
            disliked=frozenset(stats.disliked),
            recent=tuple(
                RecentTale(
                    title=t.title,
                    skill=t.skill,
                    rating=t.rating,
                    excerpt=" ".join(t.text.split())[:EXCERPT_CHARS],
                )
                for t in recent_rows
            ),
        )

        # 2. Запуск харнесса под общим бюджетом времени
        try:
            async with asyncio.timeout(self._settings.harness_timeout_s):
                result = await self._harness.run(run_input, on_progress)
        except TimeoutError as exc:
            await self._record_failure(user_id, request, RunTrace(), "error")
            raise LLMError("Превышено время генерации") from exc
        except HarnessError as exc:
            outcome = "blocked" if isinstance(exc, GuardBlocked) else "error"
            await self._record_failure(user_id, request, exc.trace or RunTrace(), outcome)
            raise

        # 3. Сохранение сказки и трассы одной транзакцией
        return await self._persist(user_id, child_id, request, result)

    async def _persist(
        self, user_id: int, child_id: int, request: TaleRequest, result: RunResult
    ) -> GeneratedTale:
        async with self._sf.begin() as session:
            tale = await repo.add_tale(
                session,
                user_id=user_id,
                child_id=child_id,
                seed_id=result.seed_id,
                mode="classic" if result.seed_id else "original",
                bedtime=request.bedtime or result.skill == BEDTIME,
                title=result.title[:200],
                text=result.body,
                skill=result.skill,
                parent_note=result.parent_note,
            )
            await repo.add_run(
                session,
                **_run_fields(user_id, tale.id, result.skill, result.trace, "ok"),
            )
        log.info(
            "tale_generated",
            user_id=user_id,
            skill=result.skill,
            seed=result.seed_id,
            chars=len(result.body),
            steps=result.trace.steps,
            tools=result.trace.tool_calls,
            revised=result.trace.revised,
            issues=result.trace.issues,
            latency_ms=result.trace.latency_ms,
            tokens_in=result.trace.usage.input_tokens,
            tokens_out=result.trace.usage.output_tokens,
            cache_read=result.trace.usage.cache_read_tokens,
            guard_tokens=result.trace.guard_usage.input_tokens
            + result.trace.guard_usage.output_tokens,
        )
        return GeneratedTale(
            id=tale.id,
            title=tale.title,
            text=tale.text,
            parent_note=tale.parent_note,
            skill=tale.skill,
        )

    async def _record_failure(
        self, user_id: int, request: TaleRequest, trace: RunTrace, outcome: str
    ) -> None:
        """Неудачные запуски тоже стоят токенов — пишем трассу, но сбой записи не должен мешать ответу."""
        try:
            skill = trace.primary_skill or request.skill
            async with self._sf.begin() as session:
                await repo.add_run(session, **_run_fields(user_id, None, skill, trace, outcome))
        except Exception:
            log.warning("run_record_failed", exc_info=True)


def _run_fields(
    user_id: int, tale_id: int | None, skill: str | None, trace: RunTrace, outcome: str
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "tale_id": tale_id,
        "skill": skill,
        "model": trace.model,
        "outcome": outcome,
        "steps": trace.steps,
        "tool_calls": list(trace.tool_calls),
        "issues": list(trace.issues),
        "revised": trace.revised,
        "critic_used": trace.critic_used,
        "input_tokens": trace.usage.input_tokens,
        "output_tokens": trace.usage.output_tokens,
        "cache_read_tokens": trace.usage.cache_read_tokens,
        "cache_write_tokens": trace.usage.cache_write_tokens,
        "latency_ms": trace.latency_ms,
    }


def _parse_length(value: str | None) -> TaleLength:
    try:
        return TaleLength(value) if value else TaleLength.NORMAL
    except ValueError:
        return TaleLength.NORMAL
