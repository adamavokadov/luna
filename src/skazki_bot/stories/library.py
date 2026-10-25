"""Загрузка и валидация библиотеки классических сюжетов (данные: knowledge/tales/classics.yaml)."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Classic(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")  # короткий: идёт в callback_data (лимит 64 байта)
    title: str
    summary: str
    beats: list[str] = Field(min_length=3)
    moral: str
    themes: list[str] = Field(min_length=1)
    min_age: int = Field(ge=1, le=12)
    max_age: int = Field(ge=1, le=12)
    scary: int = Field(ge=0, le=3)
    child_role: str
    ending_hint: str | None = None

    @model_validator(mode="after")
    def _check_ages(self) -> Classic:
        if self.min_age > self.max_age:
            raise ValueError(f"{self.id}: min_age > max_age")
        return self


@lru_cache
def load_classics() -> tuple[Classic, ...]:
    raw = files("skazki_bot.knowledge").joinpath("tales/classics.yaml").read_text(encoding="utf-8")
    classics = tuple(Classic.model_validate(item) for item in yaml.safe_load(raw))
    ids = [c.id for c in classics]
    if len(ids) != len(set(ids)):
        raise ValueError("В classics.yaml повторяются id")
    return classics


def get_classic(classic_id: str) -> Classic | None:
    return next((c for c in load_classics() if c.id == classic_id), None)


def classics_for_age(age: int) -> list[Classic]:
    return [c for c in load_classics() if c.min_age <= age <= c.max_age]
