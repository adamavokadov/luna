"""Tale knowledge base: the folk toolkit used while generating tales.

The knowledge base for tales has two parts:

* `tales/classics.yaml` - classic plots (synopses, not texts); loaded by `skazki_bot.stories`;
* `tales/folk_toolkit.yaml` - folk poetics: openings, closings, refrains, helpers, magic objects
  and lullaby lines. A few of them are picked per tale and handed to the model as optional
  building blocks (see `toolkit_prompt`).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skazki_bot.knowledge.loader import load_yaml

REFRAIN_MAX_AGE = 7  # refrains (rhythmic repeats) matter for the youngest listeners


class Entry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    text: str = Field(min_length=3, max_length=320)
    min_age: int = Field(default=2, ge=1, le=12)
    max_age: int = Field(default=10, ge=1, le=12)
    calm: bool = True  # fine for a bedtime tale
    themes: list[str] = Field(default_factory=list)  # prefer when the child's themes overlap

    @model_validator(mode="after")
    def _check_ages(self) -> Entry:
        if self.min_age > self.max_age:
            raise ValueError(f"{self.id}: min_age > max_age")
        return self


class FolkToolkit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    openings: list[Entry] = Field(min_length=5)
    closings: list[Entry] = Field(min_length=5)
    refrains: list[Entry] = Field(min_length=4)
    helpers: list[Entry] = Field(min_length=5)
    objects: list[Entry] = Field(min_length=5)
    lullabies: list[Entry] = Field(min_length=3)

    @model_validator(mode="after")
    def _unique_ids(self) -> FolkToolkit:
        ids = [e.id for group in self.groups() for e in group]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate ids in folk_toolkit.yaml: {duplicates}")
        return self

    def groups(self) -> tuple[list[Entry], ...]:
        return (
            self.openings,
            self.closings,
            self.refrains,
            self.helpers,
            self.objects,
            self.lullabies,
        )

    def __len__(self) -> int:
        return sum(len(group) for group in self.groups())


@lru_cache
def load_folk_toolkit() -> FolkToolkit:
    return FolkToolkit.model_validate(load_yaml("tales/folk_toolkit.yaml"))


@dataclass(frozen=True)
class ToolkitPick:
    opening: Entry
    closing: Entry
    refrain: Entry | None
    helper: Entry
    magic_object: Entry


def _fits(entries: Sequence[Entry], *, age: int, bedtime: bool) -> list[Entry]:
    """Entries for this age (and calm enough for bedtime); degrade gracefully, never return []."""
    allowed = [e for e in entries if e.calm or not bedtime]
    by_age = [e for e in allowed if e.min_age <= age <= e.max_age]
    return by_age or allowed or list(entries)


def _choose(entries: Sequence[Entry], themes: set[str], rng: random.Random) -> Entry:
    matching = [e for e in entries if themes & set(e.themes)]
    pool = matching if matching and rng.random() < 0.6 else entries
    return rng.choice(list(pool))


def pick_toolkit(
    toolkit: FolkToolkit,
    *,
    age: int,
    bedtime: bool,
    themes: set[str],
    rng: random.Random,
) -> ToolkitPick:
    closings = _fits(toolkit.closings, age=age, bedtime=bedtime)
    if bedtime:  # a bedtime tale may end on a lullaby line
        closings = closings + _fits(toolkit.lullabies, age=age, bedtime=True)
    refrain = None
    if age <= REFRAIN_MAX_AGE:
        refrain = _choose(_fits(toolkit.refrains, age=age, bedtime=bedtime), themes, rng)
    return ToolkitPick(
        opening=_choose(_fits(toolkit.openings, age=age, bedtime=bedtime), themes, rng),
        closing=_choose(closings, themes, rng),
        refrain=refrain,
        helper=_choose(_fits(toolkit.helpers, age=age, bedtime=bedtime), themes, rng),
        magic_object=_choose(_fits(toolkit.objects, age=age, bedtime=bedtime), themes, rng),
    )


TOOLKIT_INTRO = (
    "Фольклорные заготовки — на твой выбор: бери то, что подходит формату и сюжету, "
    "остальное пропусти. Фразы можно переработать под героя."
)


def toolkit_prompt(pick: ToolkitPick) -> str:
    """Prompt block (Russian) with the picked building blocks."""
    lines = [TOOLKIT_INTRO, f"Зачин: {pick.opening.text}", f"Концовка: {pick.closing.text}"]
    if pick.refrain is not None:
        lines.append(f"Припев-повтор: {pick.refrain.text}")
    lines.append(f"Помощник: {pick.helper.text}")
    lines.append(f"Волшебный предмет: {pick.magic_object.text}")
    return "\n".join(lines)
