"""Choosing and rendering a warm message from the knowledge base (pure, deterministic with a seed).

Message layout: Luna's opener -> the word (compliment / encouragement / proverb) -> Luna's closer.
At most two emojis per message (one in the opener, one in the closer).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

from skazki_bot.cheer import schedule
from skazki_bot.cheer.schedule import Daypart
from skazki_bot.knowledge.cheer_kb import (
    CHILD_PLACEHOLDER,
    KIND_PREFIX,
    CheerItem,
    CheerKB,
    Kind,
)

MOODS = ("tired", "anxious", "stuck", "proud")  # what the reader can pick via /cheer
KINDS: tuple[Kind, ...] = tuple(KIND_PREFIX)

_BASE_WEIGHTS: dict[Kind, float] = {"compliment": 0.4, "encouragement": 0.3, "proverb": 0.3}
_MOOD_WEIGHTS: dict[str, dict[Kind, float]] = {
    "tired": {"compliment": 0.4, "encouragement": 0.5, "proverb": 0.1},
    "anxious": {"compliment": 0.3, "encouragement": 0.5, "proverb": 0.2},
    "stuck": {"compliment": 0.2, "encouragement": 0.4, "proverb": 0.4},
    "proud": {"compliment": 0.7, "encouragement": 0.1, "proverb": 0.2},
}
_REPEAT_KIND_PENALTY = 0.25  # the same kind twice in a row is less likely
_MIN_EXACT_MOOD_ITEMS = 3  # fewer mood-specific items than this: top up with neutral ones


@dataclass(frozen=True)
class CheerMessage:
    item_id: str
    kind: Kind
    html: str  # ready for parse_mode=HTML


def _fits(item: CheerItem, *, part: Daypart | None, mood: str | None, has_child: bool) -> bool:
    """`part=None` ignores the time of day."""
    if item.child and not has_child:
        return False
    if part is not None and "any" not in item.times and part not in item.times:
        return False
    if mood is None:  # proactive message: mood-specific items are only for those who ask
        return "any" in item.moods
    return mood in item.moods or "any" in item.moods


def _candidates(
    items: Sequence[CheerItem],
    *,
    daypart: Daypart,
    mood: str | None,
    has_child: bool,
    recent: frozenset[str],
) -> list[CheerItem]:
    """Eligible items; relax recency, then time of day, rather than return nothing."""
    attempts = ((True, True), (False, True), (True, False), (False, False))
    for respect_recent, respect_daypart in attempts:
        part = daypart if respect_daypart else None
        pool = [i for i in items if _fits(i, part=part, mood=mood, has_child=has_child)]
        if respect_recent:
            pool = [i for i in pool if i.id not in recent]
        if mood is not None:
            exact = [i for i in pool if mood in i.moods]
            if len(exact) >= _MIN_EXACT_MOOD_ITEMS:
                pool = exact
        if pool:
            return pool
    return []


def pick(
    kb: CheerKB,
    *,
    daypart: Daypart,
    mood: str | None,
    child_name: str | None,
    recent: Sequence[str],
    rng: random.Random,
) -> tuple[Kind, CheerItem]:
    recent_set = frozenset(recent)
    pools = {
        kind: _candidates(
            kb.items(kind),
            daypart=daypart,
            mood=mood,
            has_child=bool(child_name),
            recent=recent_set,
        )
        for kind in KINDS
    }
    weights = dict(_MOOD_WEIGHTS.get(mood or "", _BASE_WEIGHTS))
    last_kind = kb.kind_of(recent[-1]) if recent else None
    kinds = [k for k in KINDS if pools[k]]
    if not kinds:  # cannot happen with a valid KB; degrade instead of crashing
        return "compliment", rng.choice(kb.compliments)
    kind_weights = [
        weights[k] * (_REPEAT_KIND_PENALTY if k == last_kind and len(kinds) > 1 else 1.0)
        for k in kinds
    ]
    kind = rng.choices(kinds, weights=kind_weights, k=1)[0]
    return kind, rng.choice(pools[kind])


def render(
    kb: CheerKB,
    kind: Kind,
    item: CheerItem,
    *,
    daypart: Daypart,
    mood: str | None,
    child_name: str | None,
    rng: random.Random,
) -> str:
    frames = kb.frames
    opener = rng.choice(frames.mood_openers[mood] if mood in MOODS else frames.openers[daypart])  # type: ignore[index]
    closer = rng.choice(frames.closers[daypart])
    if kind == "proverb":
        body = f"<i>«{escape(item.text.rstrip('.'), quote=False)}»</i>\n{escape(item.note or '', quote=False)}"
    else:
        body = escape(item.text, quote=False)
        if item.child:
            body = body.replace(CHILD_PLACEHOLDER, escape(child_name or "", quote=False))
    return f"{opener}\n\n{body}\n\n{closer}"


def compose(
    kb: CheerKB,
    *,
    local_hour: int,
    mood: str | None = None,
    child_name: str | None = None,
    recent: Sequence[str] = (),
    rng: random.Random | None = None,
) -> CheerMessage:
    rng = rng or random.Random()
    part = schedule.daypart(local_hour)
    chosen_mood = mood if mood in MOODS else None
    kind, item = pick(
        kb, daypart=part, mood=chosen_mood, child_name=child_name, recent=recent, rng=rng
    )
    html = render(kb, kind, item, daypart=part, mood=chosen_mood, child_name=child_name, rng=rng)
    return CheerMessage(item_id=item.id, kind=kind, html=html)
