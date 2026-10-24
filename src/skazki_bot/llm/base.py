"""Интерфейс к языковой модели для агентного цикла (harness)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(Exception):
    """Любая ошибка генерации: сеть, лимиты провайдера, отказ модели, пустой ответ."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class TurnResult:
    text: str
    tool_calls: tuple[ToolCall, ...]
    assistant_content: list[dict[str, Any]]  # блоки ответа — чтобы вернуть их в историю диалога
    stop_reason: str
    usage: Usage


Message = dict[str, Any]
TextCallback = Callable[[str], Awaitable[None]]


class ChatLLM(Protocol):
    async def turn(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_tokens: int,
        on_text: TextCallback | None = None,
    ) -> TurnResult:
        """Один ход модели: потоковый текст (on_text получает дельты) и/или вызовы инструментов."""
        ...

    async def complete(
        self, *, system: str, user: str, max_tokens: int, model: str | None = None
    ) -> tuple[str, Usage]:
        """Короткий вызов без стриминга и инструментов (критик, классификаторы)."""
        ...
