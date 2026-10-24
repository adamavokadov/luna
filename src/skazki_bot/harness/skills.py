"""Навыки (Agent Skills): папка с SKILL.md — методика написания сказки определённого формата.

Прогрессивное раскрытие, как в спецификации agentskills.io:
  1. метаданные (name + description) — в каталоге системного промпта всегда;
  2. тело SKILL.md — загружается, когда навык выбран (инструмент load_skill или выбор в меню);
  3. references/*.md — читаются по необходимости (инструмент read_skill_file).

Frontmatter соблюдает спецификацию: name, description, license, compatibility, metadata, allowed-tools.
Собственные поля проекта лежат в `metadata` (title, emoji, min-age, ... — значения-строки).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from skazki_bot.logging import get_logger

log = get_logger(__name__)

BEDTIME = "bedtime"
TOOL_NAMES = ("load_skill", "read_skill_file", "pick_classic", "get_recent_tales")

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", re.DOTALL)
REFERENCE_RE = re.compile(r"references/[\w.\-]+\.(?:md|txt)")
SPEC_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)

MAX_NAME_LEN = 64
MAX_DESCRIPTION_LEN = 300  # строже спецификации (1024): каталог живёт в системном промпте
MAX_BODY_LINES = 500
MAX_PRESETS = 8
MAX_PRESET_LEN = 40


class SkillError(ValueError):
    """Навык оформлен неверно."""


class SkillMeta(BaseModel):
    """Собственные поля проекта из `metadata` (в YAML — строки, pydantic приводит типы)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str
    emoji: str = "✨"
    min_age: int = Field(default=2, alias="min-age", ge=1, le=12)
    max_age: int = Field(default=10, alias="max-age", ge=1, le=12)
    bedtime_ok: bool = Field(default=True, alias="bedtime-ok")  # годится для «сказки на ночь»
    overlay: bool = False  # можно накладывать поверх другого формата (тон/ритм)
    menu: bool = True  # показывать в меню форматов
    input: str = Field(default="none", pattern=r"^(none|optional|required)$")
    input_prompt: str = Field(default="", alias="input-prompt")
    presets: str = ""  # варианты тем через «|»
    length_factor: float = Field(default=1.0, alias="length-factor", gt=0.2, le=2.0)
    parent_note: bool = Field(default=False, alias="parent-note")  # нужен раздел «Для родителей»
    order: int = 100


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    meta: SkillMeta
    body: str
    path: Path
    references: tuple[str, ...]  # относительные пути: references/x.md
    allowed_tools: tuple[str, ...]

    @property
    def title(self) -> str:
        return self.meta.title

    @property
    def emoji(self) -> str:
        return self.meta.emoji

    @property
    def presets(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.meta.presets.split("|") if p.strip())

    @property
    def button(self) -> str:
        return f"{self.meta.emoji} {self.meta.title}"

    def fits_age(self, age: int) -> bool:
        return self.meta.min_age <= age <= self.meta.max_age


def load_skill_dir(path: Path) -> Skill:
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        raise SkillError(f"{path.name}: нет файла SKILL.md")
    match = FRONTMATTER_RE.match(skill_file.read_text(encoding="utf-8"))
    if match is None:
        raise SkillError(f"{path.name}: SKILL.md должен начинаться с YAML-frontmatter (--- … ---)")
    try:
        front: Any = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillError(f"{path.name}: некорректный YAML во frontmatter: {exc}") from exc
    if not isinstance(front, dict):
        raise SkillError(f"{path.name}: frontmatter должен быть словарём")

    unknown = set(front) - SPEC_FIELDS
    if unknown:
        raise SkillError(
            f"{path.name}: поля {sorted(unknown)} вне спецификации — перенесите их в metadata"
        )

    name = str(front.get("name", ""))
    if not NAME_RE.fullmatch(name) or len(name) > MAX_NAME_LEN:
        raise SkillError(f"{path.name}: name «{name}» — только строчные буквы, цифры и дефисы")
    if name != path.name:
        raise SkillError(f"{path.name}: name «{name}» должен совпадать с именем папки")

    description = " ".join(str(front.get("description", "")).split())
    if not description:
        raise SkillError(f"{name}: пустой description")
    if len(description) > MAX_DESCRIPTION_LEN:
        raise SkillError(f"{name}: description длиннее {MAX_DESCRIPTION_LEN} символов")

    raw_meta = front.get("metadata") or {}
    if not isinstance(raw_meta, dict):
        raise SkillError(f"{name}: metadata должен быть словарём")
    try:
        meta = SkillMeta.model_validate({str(k): v for k, v in raw_meta.items()})
    except ValidationError as exc:
        raise SkillError(f"{name}: metadata: {exc}") from exc
    if meta.min_age > meta.max_age:
        raise SkillError(f"{name}: min-age больше max-age")
    presets = [p for p in meta.presets.split("|") if p.strip()]
    if len(presets) > MAX_PRESETS or any(len(p.strip()) > MAX_PRESET_LEN for p in presets):
        raise SkillError(
            f"{name}: не более {MAX_PRESETS} пресетов, каждый до {MAX_PRESET_LEN} символов"
        )
    if meta.input == "required" and not (meta.input_prompt or presets):
        raise SkillError(f"{name}: для input=required нужен input-prompt или presets")

    allowed = tuple(str(front.get("allowed-tools", "")).split())
    bad_tools = [t for t in allowed if t not in TOOL_NAMES]
    if bad_tools:
        raise SkillError(
            f"{name}: неизвестные инструменты {bad_tools}; доступны {list(TOOL_NAMES)}"
        )

    body = match.group(2).strip()
    if not body:
        raise SkillError(f"{name}: пустое тело SKILL.md")
    if body.count("\n") + 1 > MAX_BODY_LINES:
        raise SkillError(
            f"{name}: тело SKILL.md длиннее {MAX_BODY_LINES} строк — вынесите в references/"
        )

    refs_dir = path / "references"
    references = (
        tuple(
            f"references/{p.name}"
            for p in sorted(refs_dir.iterdir())
            if p.suffix in {".md", ".txt"}
        )
        if refs_dir.is_dir()
        else ()
    )
    missing = [r for r in set(REFERENCE_RE.findall(body)) if r not in references]
    if missing:
        raise SkillError(f"{name}: в теле упомянуты несуществующие файлы {sorted(missing)}")

    return Skill(
        name=name,
        description=description,
        meta=meta,
        body=body,
        path=path,
        references=references,
        allowed_tools=allowed,
    )


def scan_skills(root: Path) -> list[Skill]:
    if not root.is_dir():
        raise SkillError(f"Каталог навыков не найден: {root}")
    return [
        load_skill_dir(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and not child.name.startswith((".", "_"))
    ]


def builtin_skills_dir() -> Path:
    return Path(str(files("skazki_bot").joinpath("skills")))


class SkillRegistry:
    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills = {s.name: s for s in skills}

    @classmethod
    def load(cls, extra_dir: str | Path | None = None) -> SkillRegistry:
        skills = {s.name: s for s in scan_skills(builtin_skills_dir())}
        if extra_dir:
            for skill in scan_skills(Path(extra_dir)):
                if skill.name in skills:
                    log.info("skill_overridden", name=skill.name)
                skills[skill.name] = skill
        return cls(skills.values())

    def __len__(self) -> int:
        return len(self._skills)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: (s.meta.order, s.name))

    def overlays(self) -> list[Skill]:
        return [s for s in self.all() if s.meta.overlay]

    def eligible(self, age: int, *, bedtime: bool = False, menu_only: bool = False) -> list[Skill]:
        """Форматы, доступные ребёнку этого возраста (и годные для сказки на ночь, если она включена)."""
        result = []
        for skill in self.all():
            if not skill.fits_age(age):
                continue
            if bedtime and (not skill.meta.bedtime_ok or skill.name == BEDTIME):
                continue  # наложение «на ночь» уже включено
            if menu_only and not skill.meta.menu:
                continue
            result.append(skill)
        return result

    def catalog_text(self) -> str:
        """Метаданные всех навыков — уровень 1 прогрессивного раскрытия (живёт в системном промпте)."""
        lines = ["Форматы (навыки):"]
        for skill in self.all():
            lines.append(
                f"- {skill.name}: {skill.description} [возраст {skill.meta.min_age}–{skill.meta.max_age}]"
            )
        overlays = self.overlays()
        if overlays:
            lines.append(
                "\nНаложения (поправки к тону; включаются автоматически, когда родитель выбрал их в меню, "
                "— загружать их инструментом не нужно):"
            )
            lines.extend(f"- {s.name}: {s.description}" for s in overlays)
        return "\n".join(lines)

    def read_reference(self, name: str, rel_path: str) -> str:
        skill = self.get(name)
        if skill is None:
            raise SkillError(f"нет навыка «{name}»")
        if rel_path not in skill.references:  # белый список — защита от path traversal
            available = ", ".join(skill.references) or "нет"
            raise SkillError(f"у навыка «{name}» нет файла «{rel_path}». Доступны: {available}")
        return (skill.path / rel_path).read_text(encoding="utf-8")
