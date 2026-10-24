from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import TextBlockParam

from skazki_bot.llm.base import (
    LLMError,
    Message,
    TextCallback,
    ToolCall,
    ToolSpec,
    TurnResult,
    Usage,
)


def _usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=int(getattr(raw, "input_tokens", 0) or 0),
        output_tokens=int(getattr(raw, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(raw, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(raw, "cache_creation_input_tokens", 0) or 0),
    )


class AnthropicLLM:
    """Anthropic Messages API: стриминг, tool use, prompt caching."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        guard_model: str,
        timeout: float,
        client: AsyncAnthropic | None = None,
    ) -> None:
        # max_retries: SDK сам повторяет запросы при 429/5xx/сетевых сбоях с экспоненциальной паузой
        self._client = client or AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=3)
        self._model = model
        self._guard_model = guard_model

    async def turn(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_tokens: int,
        on_text: TextCallback | None = None,
    ) -> TurnResult:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
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
            raise LLMError("Модель отказалась отвечать на запрос")

        content: list[dict[str, Any]] = []
        calls: list[ToolCall] = []
        for block in final.content:
            if block.type == "text" and block.text.strip():
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_input = dict(block.input) if isinstance(block.input, dict) else {}
                content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": tool_input}
                )
                calls.append(ToolCall(id=block.id, name=block.name, input=tool_input))
        return TurnResult(
            text=text,
            tool_calls=tuple(calls),
            assistant_content=content,
            stop_reason=stop_reason,
            usage=_usage(final.usage),
        )

    async def complete(
        self, *, system: str, user: str, max_tokens: int, model: str | None = None
    ) -> tuple[str, Usage]:
        try:
            response = await self._client.messages.create(
                model=model or self._guard_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        text = "".join(b.text for b in response.content if b.type == "text")
        return text, _usage(response.usage)
