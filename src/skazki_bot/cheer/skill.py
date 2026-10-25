"""The cheer skill: an Agent Skills-format folder (SKILL.md) for Luna's warm-words behaviour.

Tale formats are loaded by `harness.skills.SkillRegistry` and shown in the tale menus. The cheer
skill is a *companion* skill: it uses the same SKILL.md layout (frontmatter + methodology body)
but has its own validator and is never offered to the tale model. Its metadata drives the
schedule (minimum gaps between messages) and the repetition memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from skazki_bot.harness.skills import (
    FRONTMATTER_RE,
    MAX_BODY_LINES,
    MAX_DESCRIPTION_LEN,
    SPEC_FIELDS,
)

SKILL_NAME = "cheer"


class CheerSkillError(ValueError):
    """The cheer SKILL.md is malformed."""


class CheerMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str
    emoji: str = "💛"
    gap_daily_h: int = Field(default=20, alias="gap-daily-h", ge=1, le=72)
    gap_few_h: int = Field(default=46, alias="gap-few-h", ge=1, le=240)
    gap_weekly_h: int = Field(default=156, alias="gap-weekly-h", ge=1, le=336)
    recent_memory: int = Field(default=30, alias="recent-memory", ge=5, le=100)

    @model_validator(mode="after")
    def _gaps_increase(self) -> CheerMeta:
        if not self.gap_daily_h < self.gap_few_h < self.gap_weekly_h:
            raise ValueError("gaps must grow: gap-daily-h < gap-few-h < gap-weekly-h")
        return self


@dataclass(frozen=True)
class CheerSkill:
    name: str
    description: str
    meta: CheerMeta
    body: str

    def gaps(self) -> dict[str, timedelta]:
        """Minimum time between two messages for each active frequency."""
        return {
            "daily": timedelta(hours=self.meta.gap_daily_h),
            "few": timedelta(hours=self.meta.gap_few_h),
            "weekly": timedelta(hours=self.meta.gap_weekly_h),
        }


def parse_cheer_skill(text: str) -> CheerSkill:
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise CheerSkillError("cheer/SKILL.md must start with YAML frontmatter (--- ... ---)")
    try:
        front: Any = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise CheerSkillError(f"invalid YAML in frontmatter: {exc}") from exc
    if not isinstance(front, dict):
        raise CheerSkillError("frontmatter must be a mapping")
    if unknown := set(front) - SPEC_FIELDS:
        raise CheerSkillError(f"fields {sorted(unknown)} are outside the spec; use metadata")
    if front.get("name") != SKILL_NAME:
        raise CheerSkillError(f"name must be '{SKILL_NAME}'")

    description = " ".join(str(front.get("description", "")).split())
    if not description or len(description) > MAX_DESCRIPTION_LEN:
        raise CheerSkillError(f"description must be 1-{MAX_DESCRIPTION_LEN} characters")

    raw_meta = front.get("metadata") or {}
    if not isinstance(raw_meta, dict):
        raise CheerSkillError("metadata must be a mapping")
    try:
        meta = CheerMeta.model_validate({str(k): v for k, v in raw_meta.items()})
    except ValidationError as exc:
        raise CheerSkillError(f"metadata: {exc}") from exc

    body = match.group(2).strip()
    if not body or body.count("\n") + 1 > MAX_BODY_LINES:
        raise CheerSkillError(f"body must be 1-{MAX_BODY_LINES} lines")
    return CheerSkill(name=SKILL_NAME, description=description, meta=meta, body=body)


def load_cheer_skill(path: Path | None = None) -> CheerSkill:
    """Load the built-in cheer skill, or a copy at `path` (SKILL.md file)."""
    if path is not None:
        return parse_cheer_skill(path.read_text(encoding="utf-8"))
    return _builtin()


@lru_cache
def _builtin() -> CheerSkill:
    raw = files("skazki_bot.cheer").joinpath("skills/cheer/SKILL.md").read_text(encoding="utf-8")
    return parse_cheer_skill(raw)
