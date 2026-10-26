"""Интерфейс к языковой модели для агентного цикла (harness)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(Exception):
    """Любая ошибка генерации: сеть, лимиты провайдера, отказ модели, пустой ответ."""


class ModelRefusal(LLMError):
    """The model declined (`stop_reason: refusal`). Carries only the policy category, never content."""

    def __init__(self, category: str | None = None) -> None:
        suffix = f" ({category})" if category else ""
        super().__init__(f"Модель отказалась отвечать на запрос{suffix}")
        self.category = category


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
    strict: bool = (
        False  # ask for schema-guaranteed inputs; the schema must stay in the strict subset
    )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class TurnResult:
    text: str
    tool_calls: tuple[ToolCall, ...]
    # ALL blocks of the reply, thinking blocks included and unmodified: they must go back with the tool
    # results (and stay append-only), otherwise the API rejects or degrades the next request
    assistant_content: list[dict[str, Any]]
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
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        model: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        """Короткий вызов без стриминга и инструментов (критик, классификаторы).

        With `schema` the reply is constrained to that JSON schema (structured outputs). A refusal or a
        reply cut off by `max_tokens` raises instead of returning text that may not match the schema.
        """
        ...
