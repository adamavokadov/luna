"""Общие типы харнесса: вход, результат, трасса, ошибки."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from skazki_bot.domain.enums import Gender, TaleLength
from skazki_bot.llm.base import LLMError, Usage


@dataclass(frozen=True)
class ChildSnapshot:
    name: str
    gender: Gender
    age: int
    interests: tuple[str, ...] = ()  # ключи из каталога интересов
    extra: str = ""


@dataclass(frozen=True)
class RecentTale:
    """Краткая «память» о прошлых сказках ребёнка — для продолжений и разнообразия."""

    title: str
    skill: str | None
    rating: int
    excerpt: str


@dataclass(frozen=True)
class RunRequest:
    skill: str | None = None  # None — формат выбирает модель (авто)
    bedtime: bool = False  # включить наложение «сказка на ночь»
    classic_id: str | None = None
    idea: str | None = None


@dataclass(frozen=True)
class RunInput:
    child: ChildSnapshot
    request: RunRequest
    length: TaleLength = TaleLength.NORMAL
    seen: Counter[str] = field(default_factory=Counter)
    liked: frozenset[str] = frozenset()
    disliked: frozenset[str] = frozenset()
    recent: tuple[RecentTale, ...] = ()


@dataclass
class RunTrace:
    model: str = ""
    steps: int = 0
    tool_calls: list[str] = field(default_factory=list)
    skills_loaded: list[str] = field(default_factory=list)  # включая наложения
    overlays: list[str] = field(default_factory=list)  # наложения («на ночь»), включённые меню
    usage: Usage = field(default_factory=Usage)  # основная модель
    guard_usage: Usage = field(default_factory=Usage)  # модель-критик
    latency_ms: int = 0
    revised: bool = False
    critic_used: bool = False
    issues: list[str] = field(default_factory=list)  # коды замечаний guard-слоя

    @property
    def primary_skill(self) -> str | None:
        """Основной формат: выбранный в меню или загруженный моделью (наложения не в счёт)."""
        return next((n for n in self.skills_loaded if n not in self.overlays), None)


@dataclass(frozen=True)
class RunResult:
    title: str
    body: str
    parent_note: str | None
    skill: str | None
    seed_id: str | None
    trace: RunTrace


class HarnessError(LLMError):
    """Сбой харнесса; к ошибке прикладывается трасса — для учёта стоимости и отладки."""

    def __init__(self, message: str, trace: RunTrace | None = None) -> None:
        super().__init__(message)
        self.trace = trace


class GuardBlocked(HarnessError):
    """Готовая сказка не прошла проверки безопасности/качества и не будет показана."""


class InputRejected(Exception):
    """Ввод родителя не принят: кризисная тема или попытка изменить инструкции."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category
