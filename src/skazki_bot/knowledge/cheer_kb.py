"""Warm-words knowledge base: compliments, encouragements, proverbs and Luna's framing lines.

Files under `knowledge/cheer/`:

* `compliments.yaml`, `encouragements.yaml`, `proverbs.yaml` - lists of `CheerItem`;
* `frames.yaml` - Luna's openers and closers by time of day and by mood.

Authoring rules (enforced by tests): Russian only; address the adult as polite «вы» in
gender-neutral forms; no role words (мама, папа...); `{child}` only as a nominative subject.
See `docs/KNOWLEDGE.md`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skazki_bot.knowledge.loader import load_yaml

Kind = Literal["compliment", "encouragement", "proverb"]
Mood = Literal["any", "tired", "anxious", "stuck", "proud"]
TimeOfDay = Literal["any", "morning", "day", "evening"]

KIND_PREFIX: dict[Kind, str] = {"compliment": "cm", "encouragement": "en", "proverb": "pr"}
CHILD_PLACEHOLDER = "{child}"
_PLACEHOLDERS = re.compile(r"\{[^}]*\}")


def _any_mood() -> list[Mood]:
    return ["any"]


def _any_time() -> list[TimeOfDay]:
    return ["any"]


class CheerItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^(cm|en|pr)\d{2,3}$")
    text: str = Field(min_length=10, max_length=280)
    note: str | None = Field(default=None, max_length=200)  # proverbs: a gentle gloss
    moods: list[Mood] = Field(default_factory=_any_mood, min_length=1)
    times: list[TimeOfDay] = Field(default_factory=_any_time, min_length=1)
    child: bool = False  # the text contains {child} (the child's name, nominative case only)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_placeholders(self) -> CheerItem:
        found = set(_PLACEHOLDERS.findall(self.text + (self.note or "")))
        if found - {CHILD_PLACEHOLDER}:
            raise ValueError(f"{self.id}: only {CHILD_PLACEHOLDER} is allowed, found {found}")
        if self.child != (CHILD_PLACEHOLDER in self.text):
            raise ValueError(f"{self.id}: `child` must be true exactly when the text has a name")
        return self


class Frames(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    openers: dict[Literal["morning", "day", "evening"], list[str]]
    mood_openers: dict[Literal["tired", "anxious", "stuck", "proud"], list[str]]
    closers: dict[Literal["morning", "day", "evening"], list[str]]

    @model_validator(mode="after")
    def _enough_lines(self) -> Frames:
        for name, group, expected in (
            ("openers", self.openers, 3),
            ("mood_openers", self.mood_openers, 4),
            ("closers", self.closers, 3),
        ):
            if len(group) != expected or any(len(lines) < 2 for lines in group.values()):
                raise ValueError(f"frames.{name}: need {expected} keys with at least 2 lines each")
        return self


class CheerKB(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    compliments: list[CheerItem] = Field(min_length=30)
    encouragements: list[CheerItem] = Field(min_length=20)
    proverbs: list[CheerItem] = Field(min_length=20)
    frames: Frames

    @model_validator(mode="after")
    def _check_ids_and_notes(self) -> CheerKB:
        for kind in KIND_PREFIX:
            for item in self.items(kind):
                if not item.id.startswith(KIND_PREFIX[kind]):
                    raise ValueError(f"{item.id}: {kind} ids must start with {KIND_PREFIX[kind]}")
        ids = [i.id for kind in KIND_PREFIX for i in self.items(kind)]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate cheer ids: {duplicates}")
        if missing := [p.id for p in self.proverbs if not p.note]:
            raise ValueError(f"proverbs need a note: {missing}")
        return self

    def items(self, kind: Kind) -> list[CheerItem]:
        return {
            "compliment": self.compliments,
            "encouragement": self.encouragements,
            "proverb": self.proverbs,
        }[kind]

    def kind_of(self, item_id: str) -> Kind | None:
        for kind, prefix in KIND_PREFIX.items():
            if item_id.startswith(prefix):
                return kind
        return None

    def __len__(self) -> int:
        return len(self.compliments) + len(self.encouragements) + len(self.proverbs)


@lru_cache
def load_cheer_kb() -> CheerKB:
    return CheerKB.model_validate(
        {
            "compliments": load_yaml("cheer/compliments.yaml"),
            "encouragements": load_yaml("cheer/encouragements.yaml"),
            "proverbs": load_yaml("cheer/proverbs.yaml"),
            "frames": load_yaml("cheer/frames.yaml"),
        }
    )
