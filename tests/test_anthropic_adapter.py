"""Настоящий адаптер Anthropic на подставном HTTP-транспорте: SSE-поток в формате Messages API."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from anthropic import AsyncAnthropic

from skazki_bot.llm.anthropic_llm import AnthropicLLM
from skazki_bot.llm.base import LLMError, ToolSpec


def sse(*events: tuple[str, dict[str, Any]]) -> bytes:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


def message_start(
    input_tokens: int = 25, cache_read: int = 0, cache_write: int = 0
) -> tuple[str, dict[str, Any]]:
    return (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
                "content": [], "stop_reason": None, "stop_sequence": None,
                "usage": {
                    "input_tokens": input_tokens, "output_tokens": 1,
                    "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": cache_write,
                },
            },
        },
    )  # fmt: skip


def text_block(index: int, *chunks: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "text", "text": ""},
            },
        )
    ]
    events += [
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": c},
            },
        )
        for c in chunks
    ]
    events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    return events


def tool_block(
    index: int, tool_id: str, name: str, *json_parts: str
) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}},
            },
        )
    ]
    events += [
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "input_json_delta", "partial_json": part},
            },
        )
        for part in json_parts
    ]
    events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    return events


def message_end(stop_reason: str, output_tokens: int = 15) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]


class Backend:
    """Подставной сервер: запоминает запросы и отдаёт заготовленный ответ."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return self.response

    def llm(self) -> AnthropicLLM:
        client = AsyncAnthropic(
            api_key="test-key",
            base_url="http://anthropic.test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
            max_retries=0,
        )
        return AnthropicLLM(
            api_key="test-key",
            model="claude-main",
            guard_model="claude-guard",
            timeout=5,
            client=client,
        )


def stream_response(*events: tuple[str, dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(*events))


async def test_streams_text_and_maps_usage_and_request() -> None:
    backend = Backend(
        stream_response(
            message_start(input_tokens=25, cache_read=300, cache_write=40),
            *text_block(0, "Жил-был ", "малыш."),
            *message_end("end_turn", output_tokens=15),
        )
    )
    chunks: list[str] = []

    async def on_text(delta: str) -> None:
        chunks.append(delta)

    result = await backend.llm().turn(
        system="СИСТЕМА",
        messages=[{"role": "user", "content": "привет"}],
        tools=[],
        max_tokens=777,
        on_text=on_text,
    )

    assert chunks == ["Жил-был ", "малыш."]  # стриминг по дельтам
    assert result.text == "Жил-был малыш."
    assert result.stop_reason == "end_turn"
    assert result.tool_calls == ()
    assert result.assistant_content == [{"type": "text", "text": "Жил-был малыш."}]
    usage = result.usage
    assert (
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
    ) == (25, 15, 300, 40)

    sent = backend.requests[0]
    assert sent["model"] == "claude-main"
    assert sent["max_tokens"] == 777
    assert sent["stream"] is True
    assert sent["system"] == [
        {"type": "text", "text": "СИСТЕМА", "cache_control": {"type": "ephemeral"}}
    ]
    assert sent["messages"] == [{"role": "user", "content": "привет"}]
    assert "tools" not in sent  # без инструментов схема не отправляется


async def test_tool_use_is_parsed_and_tools_are_sent() -> None:
    backend = Backend(
        stream_response(
            message_start(),
            *text_block(0, "Загружаю."),
            *tool_block(1, "toolu_42", "load_skill", '{"name": "orig', 'inal"}'),
            *message_end("tool_use"),
        )
    )
    spec = ToolSpec(
        name="load_skill",
        description="Загрузить навык",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    )
    result = await backend.llm().turn(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[spec], max_tokens=100
    )

    assert result.stop_reason == "tool_use"
    (call,) = result.tool_calls
    assert (call.id, call.name, call.input) == ("toolu_42", "load_skill", {"name": "original"})
    assert result.assistant_content == [
        {"type": "text", "text": "Загружаю."},
        {"type": "tool_use", "id": "toolu_42", "name": "load_skill", "input": {"name": "original"}},
    ]
    assert backend.requests[0]["tools"] == [
        {"name": "load_skill", "description": "Загрузить навык", "input_schema": spec.input_schema}
    ]


async def test_tool_only_turn_has_no_empty_text_block() -> None:
    backend = Backend(
        stream_response(
            message_start(),
            *tool_block(0, "toolu_1", "get_recent_tales", "{}"),
            *message_end("tool_use"),
        )
    )
    result = await backend.llm().turn(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=50
    )
    assert [b["type"] for b in result.assistant_content] == [
        "tool_use"
    ]  # пустые text-блоки API не принимает


async def test_tool_exchange_is_passed_back_as_is() -> None:
    backend = Backend(
        stream_response(message_start(), *text_block(0, "Готово."), *message_end("end_turn"))
    )
    history: list[dict[str, Any]] = [
        {"role": "user", "content": "x"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "load_skill",
                    "input": {"name": "original"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "тело", "is_error": False}
            ],
        },
    ]
    await backend.llm().turn(system="s", messages=history, tools=[], max_tokens=50)
    assert backend.requests[0]["messages"] == history


async def test_refusal_is_an_error() -> None:
    backend = Backend(
        stream_response(message_start(), *text_block(0, "Не могу."), *message_end("refusal"))
    )
    with pytest.raises(LLMError, match="отказалась"):
        await backend.llm().turn(
            system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=50
        )


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_api_errors_become_llm_errors(status: int) -> None:
    error = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "плохой запрос"},
    }
    backend = Backend(httpx.Response(status, json=error))
    with pytest.raises(LLMError):
        await backend.llm().turn(
            system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=50
        )
    with pytest.raises(LLMError):
        await backend.llm().complete(system="s", user="x", max_tokens=50)


async def test_complete_uses_guard_model_and_returns_text() -> None:
    body = {
        "id": "msg_2", "type": "message", "role": "assistant", "model": "claude-guard",
        "content": [{"type": "text", "text": '{"ok": true, "issues": []}'}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 60, "output_tokens": 8},
    }  # fmt: skip
    backend = Backend(httpx.Response(200, json=body))
    llm = backend.llm()

    text, usage = await llm.complete(system="критик", user="сказка", max_tokens=700)
    assert text == '{"ok": true, "issues": []}'
    assert (usage.input_tokens, usage.output_tokens) == (60, 8)
    assert backend.requests[0]["model"] == "claude-guard"
    assert backend.requests[0]["system"] == "критик"
    assert "stream" not in backend.requests[0]

    await llm.complete(system="s", user="u", max_tokens=10, model="claude-other")
    assert backend.requests[1]["model"] == "claude-other"
