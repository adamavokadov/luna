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
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skazki_bot.domain.age import profile_for_age
from skazki_bot.knowledge.loader import load_yaml

Origin = Literal[
    "african",
    "ashanti",
    "aztec",
    "azerbaijani",
    "cherokee",
    "chinese",
    "chukchi",
    "cossack",
    "efik",
    "estonian",
    "filipino",
    "finnish",
    "french",
    "greek",
    "gunai",
    "hungarian",
    "igbo",
    "indian",
    "indonesian",
    "irish",
    "japanese",
    "kalmyk",
    "korean",
    "latvian",
    "lithuanian",
    "maori",
    "northwest_coast",
    "norwegian",
    "portuguese",
    "russian",
    "turkish",
    "ukrainian",
    "uzbek",
    "vietnamese",
    "zulu",
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
MOTIF_WEIGHT = 1.5  # per matching motif; a theme match is worth 2.0
IDEA_MOTIF_WEIGHT = 5.0  # a value the parent named outweighs the child's interests


class Collection(BaseModel):
    """Where a plot was read: provenance only, never a source of text.

    A collection with no publisher and no year is an oral tradition: the plot is known from many
    recordings and retellings, written from general knowledge and not tied to one edition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]{1,30}$")
    title: str = Field(min_length=3, max_length=200)
    publisher: str | None = Field(default=None, min_length=2, max_length=80)
    year: int | None = Field(default=None, ge=1800, le=2100)

    @model_validator(mode="after")
    def _both_or_neither(self) -> Collection:
        if (self.publisher is None) != (self.year is None):
            raise ValueError(
                f"{self.id}: give both publisher and year, or neither (oral tradition)"
            )
        return self


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


def _seen_counter(seen: Mapping[str, int] | Iterable[str]) -> Counter[str]:
    """Accept a Counter or mapping (from the tale history) as well as a plain list of ids."""
    if isinstance(seen, Mapping):
        return Counter({k: int(v) for k, v in seen.items()})
    return Counter(seen)


def _score(
    source: FolkSource,
    themes: set[str],
    motifs: set[str],
    seen: Counter[str],
    liked: frozenset[str],
    disliked: frozenset[str],
    motif_weight: float = MOTIF_WEIGHT,
) -> float:
    value = 2.0 * len(set(source.themes) & themes) + motif_weight * len(set(source.motifs) & motifs)
    times = seen.get(source.id, 0)
    value += 3.0 if times == 0 else -2.0 * times
    if source.id in liked:
        value += 2.0
    if source.id in disliked:
        value -= 5.0
    return value


def find_folk_sources(
    sources: Sequence[FolkSource],
    *,
    age: int,
    bedtime: bool = False,
    themes: Iterable[str] = (),
    motifs: Iterable[str] = (),
    seen: Mapping[str, int] | Iterable[str] = (),
    liked: Iterable[str] = (),
    disliked: Iterable[str] = (),
    limit: int = 3,
    rng: random.Random | None = None,
    motif_weight: float = MOTIF_WEIGHT,
) -> list[FolkSource]:
    """Up to `limit` different plots: best by score, ties broken by `rng` (deterministic if seeded)."""
    rng = rng or random.Random()
    theme_set, motif_set = set(themes), set(motifs)
    history, likes, dislikes = _seen_counter(seen), frozenset(liked), frozenset(disliked)
    pool = eligible_sources(sources, age=age, bedtime=bedtime)
    shuffled = rng.sample(pool, k=len(pool))  # stable tie-breaking order for sorted()
    ranked = sorted(
        shuffled,
        key=lambda s: _score(s, theme_set, motif_set, history, likes, dislikes, motif_weight),
        reverse=True,
    )
    return ranked[: max(limit, 0)]


def pick_folk_source(
    sources: Sequence[FolkSource],
    *,
    age: int,
    bedtime: bool = False,
    themes: Iterable[str] = (),
    motifs: Iterable[str] = (),
    seen: Mapping[str, int] | Iterable[str] = (),
    liked: Iterable[str] = (),
    disliked: Iterable[str] = (),
    rng: random.Random | None = None,
    top_k: int = 3,
    motif_weight: float = MOTIF_WEIGHT,
) -> FolkSource | None:
    """One plot for one tale: weighted random among the top-k, so the choice is not always the same.

    Same idea as `select_classic`: the best-scoring plots are likely, but not certain.
    """
    rng = rng or random.Random()
    theme_set, motif_set = set(themes), set(motifs)
    history, likes, dislikes = _seen_counter(seen), frozenset(liked), frozenset(disliked)
    top = find_folk_sources(
        sources,
        age=age,
        bedtime=bedtime,
        themes=theme_set,
        motifs=motif_set,
        seen=history,
        liked=likes,
        disliked=dislikes,
        limit=top_k,
        rng=rng,
        motif_weight=motif_weight,
    )
    if not top:
        return None
    scores = [_score(s, theme_set, motif_set, history, likes, dislikes, motif_weight) for s in top]
    floor = min(scores)
    return rng.choices(top, weights=[v - floor + 1.0 for v in scores], k=1)[0]


class IdeaHint(BaseModel):
    """A value or topic a parent may name (stems, lowercase) and the plot motifs / themes it points to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stems: list[str] = Field(min_length=1)
    motifs: list[Motif] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_empty(self) -> IdeaHint:
        if not self.motifs and not self.themes:
            raise ValueError("an idea hint needs motifs or themes")
        if any(stem != stem.lower() or len(stem) < 3 for stem in self.stems):
            raise ValueError("stems are lowercase and at least 3 characters")
        return self


@lru_cache
def load_idea_hints() -> tuple[IdeaHint, ...]:
    raw = load_yaml("tales/folk_idea_hints.yaml")
    return tuple(IdeaHint.model_validate(item) for item in raw)


def hints_for_idea(
    idea: str, hints: Sequence[IdeaHint] | None = None
) -> tuple[list[str], list[str]]:
    """Motifs and themes that a parent's free-text idea points to (empty if it names nothing known)."""
    text = idea.lower().replace("ё", "е")
    motifs: list[str] = []
    themes: list[str] = []
    for hint in hints if hints is not None else load_idea_hints():
        if any(stem.replace("ё", "е") in text for stem in hint.stems):
            motifs += [m for m in hint.motifs if m not in motifs]
            themes += [t for t in hint.themes if t not in themes]
    return motifs, themes


FOLK_SOURCE_INTRO = (
    "Народный сюжет-основа. Перескажи его заново для этого ребёнка своими словами: "
    "сохрани ход событий и главную мысль, но смени героев, место и детали и вплети ребёнка. "
    "Не копируй ничьих готовых текстов и не называй сборники. "
    "Если сюжет не ложится на выбранный формат, возьми одно звено как зерно для своей сказки."
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
