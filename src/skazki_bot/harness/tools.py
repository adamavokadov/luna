"""Инструменты агента. Все работают поверх заранее загруженных данных — в БД во время генерации не ходим."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from skazki_bot.harness.prompts import classic_block
from skazki_bot.harness.skills import BEDTIME, TOOL_NAMES, Skill, SkillError, SkillRegistry
from skazki_bot.harness.types import RecentTale
from skazki_bot.llm.base import ToolCall, ToolSpec
from skazki_bot.stories.library import Classic
from skazki_bot.stories.selector import SelectionContext, select_many

MAX_LOADED_SKILLS = 2
EXCERPT_CHARS = 350

TOOL_SPECS: dict[str, ToolSpec] = {
    "load_skill": ToolSpec(
        name="load_skill",
        description=(
            "Загрузить полную инструкцию навыка (формата сказки) по имени из каталога. "
            "Вызови перед тем, как писать сказку, если формат не задан в запросе."
        ),
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Имя навыка из каталога"}},
            "required": ["name"],
        },
    ),
    "read_skill_file": ToolSpec(
        name="read_skill_file",
        description="Прочитать дополнительный файл загруженного навыка (references/…), если он нужен.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Имя навыка"},
                "path": {"type": "string", "description": "Путь вида references/файл.md"},
            },
            "required": ["name", "path"],
        },
    ),
    "pick_classic": ToolSpec(
        name="pick_classic",
        description=(
            "Подобрать классический сюжет-основу (конспект) под возраст и интересы ребёнка; "
            "учитывает, что уже рассказывали."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 3,
                    "description": "Сколько сюжетов",
                },
                "theme": {
                    "type": "string",
                    "description": "Желаемая тема: animals, forest, magic, sea, winter…",
                },
            },
        },
    ),
    "get_recent_tales": ToolSpec(
        name="get_recent_tales",
        description=(
            "Недавние сказки этого ребёнка: название, формат, оценка, начало текста. "
            "Нужно для продолжений и чтобы не повторяться."
        ),
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
        },
    ),
}
assert tuple(TOOL_SPECS) == TOOL_NAMES  # список имён в skills.py и описания не должны расходиться


@dataclass(frozen=True)
class ToolOutput:
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    registry: SkillRegistry
    age: int
    bedtime: bool
    classics: Sequence[Classic]
    selection: SelectionContext
    recent: Sequence[RecentTale]
    rng: random.Random
    loaded: list[str]  # общий с трассой список загруженных навыков
    words_for: Callable[[Skill], int]  # рекомендуемый объём сказки с этим навыком
    max_result_chars: int = 6000


class ToolExecutor:
    def __init__(self, ctx: ToolContext) -> None:
        self._ctx = ctx

    async def run(self, call: ToolCall) -> ToolOutput:
        handler = {
            "load_skill": self._load_skill,
            "read_skill_file": self._read_skill_file,
            "pick_classic": self._pick_classic,
            "get_recent_tales": self._get_recent_tales,
        }.get(call.name)
        if handler is None:
            return ToolOutput(f"Неизвестный инструмент «{call.name}»", is_error=True)
        try:
            output = handler(call.input)
        except (SkillError, ValueError, TypeError, KeyError) as exc:
            return ToolOutput(f"Ошибка: {exc}", is_error=True)
        if len(output.content) > self._ctx.max_result_chars:
            return ToolOutput(
                output.content[: self._ctx.max_result_chars] + "\n…(обрезано)", output.is_error
            )
        return output

    # --- реализации ------------------------------------------------------------------------------
    def _eligible_names(self) -> str:
        names = [
            s.name for s in self._ctx.registry.eligible(self._ctx.age, bedtime=self._ctx.bedtime)
        ]
        return ", ".join(names)

    def _load_skill(self, args: dict[str, Any]) -> ToolOutput:
        ctx = self._ctx
        name = str(args.get("name", "")).strip()
        skill = ctx.registry.get(name)
        eligible = ctx.registry.eligible(ctx.age, bedtime=ctx.bedtime)
        if skill is None:
            return ToolOutput(
                f"Нет навыка «{name}». Доступные: {self._eligible_names()}", is_error=True
            )
        if skill not in eligible:
            return ToolOutput(
                f"Навык «{name}» не подходит под возраст ребёнка или сказку на ночь. "
                f"Доступные: {self._eligible_names()}",
                is_error=True,
            )
        if name in ctx.loaded:
            return ToolOutput(f"Навык «{name}» уже загружен — пиши сказку.", is_error=True)
        if len(ctx.loaded) >= MAX_LOADED_SKILLS:
            return ToolOutput(
                f"Уже загружено максимум {MAX_LOADED_SKILLS} навыка — пиши сказку.", is_error=True
            )
        ctx.loaded.append(name)

        parts = [
            skill.body,
            f"\nРекомендуемый объём с этим навыком: примерно {ctx.words_for(skill)} слов.",
        ]
        if skill.references:
            parts.append(
                "Дополнительные файлы (читай через read_skill_file, если нужно): "
                + ", ".join(skill.references)
            )
        if skill.meta.input == "required" and not skill.presets:
            parts.append("Если тема не задана в <idea>, выбери подходящую по интересам ребёнка.")
        return ToolOutput("\n".join(parts))

    def _read_skill_file(self, args: dict[str, Any]) -> ToolOutput:
        name = str(args.get("name", "")).strip()
        path = str(args.get("path", "")).strip()
        if name not in self._ctx.loaded:
            return ToolOutput(f"Сначала загрузите навык «{name}» (load_skill).", is_error=True)
        return ToolOutput(self._ctx.registry.read_reference(name, path))

    def _pick_classic(self, args: dict[str, Any]) -> ToolOutput:
        ctx = self._ctx
        count = min(max(int(args.get("count", 1)), 1), 3)
        theme = str(args.get("theme", "")).strip().lower()
        selection = ctx.selection
        if theme:
            selection = SelectionContext(
                age=selection.age,
                themes=selection.themes | {theme},
                seen=selection.seen,
                liked=selection.liked,
                disliked=selection.disliked,
                bedtime=selection.bedtime,
            )
        picked = select_many(ctx.classics, selection, ctx.rng, count)
        if not picked:
            return ToolOutput(
                "Подходящих классических сюжетов нет — придумай оригинальный.", is_error=True
            )
        blocks = [f"[{c.id}]\n{classic_block(c)}" for c in picked]
        return ToolOutput("\n\n".join(blocks))

    def _get_recent_tales(self, args: dict[str, Any]) -> ToolOutput:
        limit = min(max(int(args.get("limit", 3)), 1), 5)
        recent = list(self._ctx.recent)[:limit]
        if not recent:
            return ToolOutput("У этого ребёнка пока нет сказок — это первая.")
        marks = {1: "понравилась", -1: "не понравилась", 0: "без оценки"}
        lines = []
        for i, tale in enumerate(recent, start=1):
            lines.append(
                f"{i}) «{tale.title}» — формат: {tale.skill or 'не определён'}; "
                f"оценка: {marks.get(tale.rating, 'без оценки')}\n   Начало: {tale.excerpt}"
            )
        return ToolOutput("\n".join(lines))


def tool_specs_for(names: Sequence[str]) -> list[ToolSpec]:
    return [TOOL_SPECS[n] for n in names if n in TOOL_SPECS]


__all__ = [
    "BEDTIME",
    "MAX_LOADED_SKILLS",
    "TOOL_SPECS",
    "ToolContext",
    "ToolExecutor",
    "ToolOutput",
    "tool_specs_for",
]
