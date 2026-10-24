"""Подбор классического сюжета под конкретного ребёнка (без LLM: быстро и детерминированно)."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from skazki_bot.domain.age import profile_for_age
from skazki_bot.stories.library import Classic


@dataclass(frozen=True)
class SelectionContext:
    age: int
    themes: set[str] = field(default_factory=set)  # темы из интересов ребёнка
    seen: Counter[str] = field(default_factory=Counter)
    liked: set[str] = field(default_factory=set)
    disliked: set[str] = field(default_factory=set)
    bedtime: bool = False


def _max_scary(ctx: SelectionContext) -> int:
    limit = profile_for_age(ctx.age).max_scary
    return min(limit, 1) if ctx.bedtime else limit


def eligible(classics: Sequence[Classic], ctx: SelectionContext) -> list[Classic]:
    """Сюжеты по возрасту и «страшности»; если ничего нет — ближайшие по возрасту."""
    limit = _max_scary(ctx)
    fits = [c for c in classics if c.min_age <= ctx.age <= c.max_age and c.scary <= limit]
    if fits:
        return fits
    calm = [c for c in classics if c.scary <= limit]
    pool = calm or list(classics)
    return sorted(pool, key=lambda c: min(abs(c.min_age - ctx.age), abs(c.max_age - ctx.age)))[:5]


def score(classic: Classic, ctx: SelectionContext) -> float:
    value = 2.0 * len(set(classic.themes) & ctx.themes)
    times = ctx.seen.get(classic.id, 0)
    value += 3.0 if times == 0 else -2.0 * times
    if classic.id in ctx.liked:
        value += 2.0
    if classic.id in ctx.disliked:
        value -= 5.0
    return value


def select_classic(
    classics: Sequence[Classic],
    ctx: SelectionContext,
    rng: random.Random | None = None,
    top_k: int = 3,
) -> Classic:
    """Берём top-k по очкам и выбираем случайно с весами — чтобы выдача не была однообразной."""
    rng = rng or random.Random()
    pool = eligible(classics, ctx)
    ranked = sorted(pool, key=lambda c: score(c, ctx), reverse=True)[:top_k]
    floor = min(score(c, ctx) for c in ranked)
    weights = [score(c, ctx) - floor + 1.0 for c in ranked]
    return rng.choices(ranked, weights=weights, k=1)[0]


def select_many(
    classics: Sequence[Classic],
    ctx: SelectionContext,
    rng: random.Random | None = None,
    count: int = 1,
) -> list[Classic]:
    """Несколько разных сюжетов (для инструмента pick_classic)."""
    picked: list[Classic] = []
    for _ in range(count):
        remaining = [c for c in classics if c not in picked]
        if not remaining:
            break
        picked.append(select_classic(remaining, ctx, rng))
    return picked
