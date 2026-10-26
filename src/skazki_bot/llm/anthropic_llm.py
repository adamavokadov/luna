from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import OutputConfigParam, TextBlockParam

from skazki_bot.config import Effort, ThinkingMode, resolve_thinking
from skazki_bot.llm.base import (
    LLMError,
    Message,
    ModelRefusal,
    TextCallback,
    ToolCall,
    ToolSpec,
    TurnResult,
    Usage,
)

# Thinking tokens are billed as output and count toward max_tokens. Adaptive thinking may spend some of the
# budget before the first word of the tale, so it gets headroom; `between_tools` does not think up front.
THINKING_HEADROOM = 2500


def _usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=int(getattr(raw, "input_tokens", 0) or 0),
        output_tokens=int(getattr(raw, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(raw, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(raw, "cache_creation_input_tokens", 0) or 0),
    )


def _refusal(message: Any) -> ModelRefusal:
    details = getattr(message, "stop_details", None)
    category = getattr(details, "category", None)
    return ModelRefusal(str(category) if category else None)


def _assistant_blocks(content: Sequence[Any]) -> tuple[list[dict[str, Any]], list[ToolCall]]:
    """Reply blocks for the next request, in order. Everything except text and tool_use (thinking,
    redacted_thinking, anything newer) is passed through unmodified: the API checks those blocks."""
    blocks: list[dict[str, Any]] = []
    calls: list[ToolCall] = []
    for block in content:
        if block.type == "text":
            if block.text.strip():  # the API does not accept empty text blocks
                blocks.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            tool_input = dict(block.input) if isinstance(block.input, dict) else {}
            blocks.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": tool_input}
            )
            calls.append(ToolCall(id=block.id, name=block.name, input=tool_input))
        else:
            blocks.append(block.model_dump(mode="json", exclude_none=True))
    return blocks, calls


class AnthropicLLM:
    """Anthropic Messages API for Claude 5.x: streaming, adaptive thinking with effort, strict tool use,
    structured outputs for classifiers, prompt caching, refusal categories."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        guard_model: str,
        timeout: float,
        effort: Effort = "medium",
        guard_effort: Effort = "low",
        thinking: ThinkingMode = "auto",
        strict_tools: bool = True,
        client: AsyncAnthropic | None = None,
    ) -> None:
        # max_retries: SDK сам повторяет запросы при 429/5xx/сетевых сбоях с экспоненциальной паузой
        self._client = client or AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=3)
        self._model = model
        self._guard_model = guard_model
        self._effort = effort
        self._guard_effort = guard_effort
        self._thinking = resolve_thinking(model, thinking)
        self._strict_tools = strict_tools

    async def turn(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_tokens: int,
        on_text: TextCallback | None = None,
    ) -> TurnResult:
        headroom = THINKING_HEADROOM if self._thinking == "adaptive" else 0
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens + headroom,
            # Claude 5.5 thinks by default at `high` effort: say explicitly how much we want
            "thinking": {"type": self._thinking},
            "output_config": {"effort": self._effort},
            # Системный промпт (правила + каталог навыков) статичен — помечаем для prompt caching:
            # сработает, когда префикс превысит минимальную кэшируемую длину модели
            "system": [
                TextBlockParam(type="text", text=system, cache_control={"type": "ephemeral"})
            ],
            "messages": list(messages),
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                | ({"strict": True} if t.strict and self._strict_tools else {})
                for t in tools
            ]
        text = ""
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for chunk in stream.text_stream:
                    text += chunk
                    if on_text is not None:
                        await on_text(chunk)
                final = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        stop_reason = str(final.stop_reason)
        if stop_reason == "refusal":
            raise _refusal(final)
        if stop_reason == "model_context_window_exceeded":
            raise LLMError("Контекст модели переполнен")

        content, calls = _assistant_blocks(final.content)
        return TurnResult(
            text=text,
            tool_calls=tuple(calls),
            assistant_content=content,
            stop_reason=stop_reason,
            usage=_usage(final.usage),
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        model: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        output_config: OutputConfigParam = {"effort": self._guard_effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            response = await self._client.messages.create(
                model=model or self._guard_model,
                max_tokens=max_tokens + THINKING_HEADROOM,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
            )
        except anthropic.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        stop_reason = str(response.stop_reason)
        if stop_reason == "refusal":
            raise _refusal(response)
        if schema is not None and stop_reason == "max_tokens":
            raise LLMError("Структурированный ответ оборван по max_tokens")
        text = "".join(b.text for b in response.content if b.type == "text")
        return text, _usage(response.usage)
