"""Folk sources: world folk plots as raw material for composing new tales.

`tales/world_folk.yaml` holds *our own* synopses of traditional plots from many peoples, cut into
the smallest meaningful story units (`beats`, one event each). They are not texts: nothing is
quoted from the collections they were read in (see `docs/FOLK_SOURCES.md`). The bot may retell a
plot from scratch for a given child, or take a single beat as a seed for an original tale.

Nothing here talks to the model by itself: `find_folk_sources` picks plots by age, bedtime,
interests and history, and `folk_source_block` renders one as a Russian prompt block.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skazki_bot.domain.age import profile_for_age
from skazki_bot.knowledge.loader import load_yaml

Origin = Literal[
    "azerbaijani",
    "chinese",
    "chukchi",
    "cossack",
    "estonian",
    "french",
    "hungarian",
    "japanese",
    "kalmyk",
    "latvian",
    "lithuanian",
    "russian",
    "ukrainian",
    "uzbek",
]
Kind = Literal["animal", "wonder", "everyday", "trickster", "legend", "epic", "parable"]
Motif = Literal[
    "kindness_rewarded",
    "greed_punished",
    "cleverness_wins",
    "magic_gift",
    "helper_animal",
    "transformation",
    "trial_of_wit",
    "origin_story",
    "community",
    "home_and_belonging",
    "honesty",
    "humility",
    "perseverance",
    "courage",
    "caution",
    "foolishness",
    "three_wishes",
    "misuse_of_gift",
]

MIN_BEATS = 4
MAX_BEATS = 9
HINT_REQUIRED_FROM_SCARY = 2  # a scary plot must say how its harsh places are softened
BEDTIME_MAX_SCARY = 1


class Collection(BaseModel):
    """Where a plot was read: provenance only, never a source of text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]{1,30}$")
    title: str = Field(min_length=3, max_length=200)
    publisher: str = Field(min_length=2, max_length=80)
    year: int = Field(ge=1800, le=2100)


class FolkSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")  # short: it may travel in callback data
    title: str = Field(min_length=3, max_length=80)
    origin: Origin
    kind: Kind
    collection: str
    summary: str = Field(min_length=20, max_length=300)
    beats: list[str] = Field(min_length=MIN_BEATS, max_length=MAX_BEATS)
    moral: str = Field(min_length=10, max_length=200)
    themes: list[str] = Field(min_length=1)
    motifs: list[Motif] = Field(min_length=1)
    min_age: int = Field(ge=1, le=12)
    max_age: int = Field(ge=1, le=12)
    scary: int = Field(ge=0, le=3)
    calm: bool  # fine for a bedtime tale
    child_role: str = Field(min_length=10, max_length=240)
    ending_hint: str | None = Field(default=None, min_length=10, max_length=400)

    @model_validator(mode="after")
    def _check(self) -> FolkSource:
        if self.min_age > self.max_age:
            raise ValueError(f"{self.id}: min_age > max_age")
        too_long = [b for b in self.beats if not 15 <= len(b) <= 180]
        if too_long:
            raise ValueError(f"{self.id}: a beat must be 15-180 characters: {too_long[0][:40]!r}")
        if self.scary >= HINT_REQUIRED_FROM_SCARY and not self.ending_hint:
            raise ValueError(f"{self.id}: scary >= {HINT_REQUIRED_FROM_SCARY} needs an ending_hint")
        if self.calm and self.scary > BEDTIME_MAX_SCARY:
            raise ValueError(f"{self.id}: a calm plot cannot be scary > {BEDTIME_MAX_SCARY}")
        return self

    def text_fields(self) -> list[str]:
        """Every free-text field, for authoring-rule checks."""
        fields = [self.title, self.summary, self.moral, self.child_role, *self.beats]
        return [*fields, self.ending_hint] if self.ending_hint else fields


class FolkSources(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    collections: list[Collection] = Field(min_length=1)
    tales: list[FolkSource] = Field(min_length=1)

    @model_validator(mode="after")
    def _links(self) -> FolkSources:
        ids = [t.id for t in self.tales]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate ids in world_folk.yaml: {duplicates}")
        collection_ids = [c.id for c in self.collections]
        if len(collection_ids) != len(set(collection_ids)):
            raise ValueError("duplicate collection ids in world_folk.yaml")
        unknown = sorted({t.collection for t in self.tales} - set(collection_ids))
        if unknown:
            raise ValueError(f"unknown collections in world_folk.yaml: {unknown}")
        return self

    def __len__(self) -> int:
        return len(self.tales)


@lru_cache
def load_folk_sources() -> FolkSources:
    return FolkSources.model_validate(load_yaml("tales/world_folk.yaml"))


def _max_scary(age: int, bedtime: bool) -> int:
    limit = profile_for_age(age).max_scary
    return min(limit, BEDTIME_MAX_SCARY) if bedtime else limit


def eligible_sources(
    sources: Sequence[FolkSource], *, age: int, bedtime: bool = False
) -> list[FolkSource]:
    """Plots for this age (and calm enough for bedtime); never empty while `sources` is not."""
    limit = _max_scary(age, bedtime)
    fits = [
        s
        for s in sources
        if s.min_age <= age <= s.max_age and s.scary <= limit and (s.calm or not bedtime)
    ]
    if fits:
        return fits
    calm = [s for s in sources if s.scary <= limit and (s.calm or not bedtime)]
    pool = calm or list(sources)
    return sorted(pool, key=lambda s: min(abs(s.min_age - age), abs(s.max_age - age)))[:5]


def _score(source: FolkSource, themes: set[str], motifs: set[str], seen: Iterable[str]) -> float:
    value = 2.0 * len(set(source.themes) & themes) + 1.5 * len(set(source.motifs) & motifs)
    times = list(seen).count(source.id)
    return value + (3.0 if times == 0 else -2.0 * times)


def find_folk_sources(
    sources: Sequence[FolkSource],
    *,
    age: int,
    bedtime: bool = False,
    themes: Iterable[str] = (),
    motifs: Iterable[str] = (),
    seen: Iterable[str] = (),
    limit: int = 3,
    rng: random.Random | None = None,
) -> list[FolkSource]:
    """Up to `limit` different plots: best by score, ties broken by `rng` (deterministic if seeded)."""
    rng = rng or random.Random()
    theme_set, motif_set, seen_ids = set(themes), set(motifs), list(seen)
    pool = eligible_sources(sources, age=age, bedtime=bedtime)
    shuffled = rng.sample(pool, k=len(pool))  # stable tie-breaking order for sorted()
    ranked = sorted(shuffled, key=lambda s: _score(s, theme_set, motif_set, seen_ids), reverse=True)
    return ranked[: max(limit, 0)]


FOLK_SOURCE_INTRO = (
    "Народный сюжет-основа. Перескажи его заново для этого ребёнка своими словами: "
    "меняй героев, место и детали, не копируй ничьих готовых текстов. "
    "Можно взять только одно звено сюжета как зерно для своей сказки."
)


def folk_source_block(source: FolkSource) -> str:
    """Prompt block (Russian) with one plot: summary, beats, moral, how to weave the child in."""
    beats = "\n".join(f"{i}. {beat}" for i, beat in enumerate(source.beats, start=1))
    lines = [
        FOLK_SOURCE_INTRO,
        f"Название: {source.title}",
        f"Кратко: {source.summary}",
        "Звенья сюжета:",
        beats,
        f"Главная мысль: {source.moral}",
        f"Как вплести ребёнка: {source.child_role}",
    ]
    if source.ending_hint:
        lines.append(f"Про финал: {source.ending_hint}")
    return "\n".join(lines)
