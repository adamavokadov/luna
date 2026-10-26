"""Настоящий адаптер Anthropic на подставном HTTP-транспорте: SSE-поток в формате Messages API."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from anthropic import AsyncAnthropic

from skazki_bot.llm.anthropic_llm import THINKING_HEADROOM, AnthropicLLM
from skazki_bot.llm.base import LLMError, ModelRefusal, ToolSpec


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

    def llm(self, **overrides: Any) -> AnthropicLLM:
        client = AsyncAnthropic(
            api_key="test-key",
            base_url="http://anthropic.test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
            max_retries=0,
        )
        settings: dict[str, Any] = {
            "api_key": "test-key",
            "model": "claude-main",
            "guard_model": "claude-guard",
            "timeout": 5,
            "client": client,
        } | overrides
        return AnthropicLLM(**settings)


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
    # an unknown model gets adaptive thinking, so max_tokens leaves room for it
    assert sent["max_tokens"] == 777 + THINKING_HEADROOM
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"] == {"effort": "medium"}
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


def thinking_block(index: int, signature: str, *thoughts: str) -> list[tuple[str, dict[str, Any]]]:
    start = {"type": "thinking", "thinking": "", "signature": ""}
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "content_block_start",
            {"type": "content_block_start", "index": index, "content_block": start},
        )
    ]
    events += [
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "thinking_delta", "thinking": t},
            },
        )
        for t in thoughts
    ]
    events.append(
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "signature_delta", "signature": signature},
            },
        )
    )
    events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    return events


async def test_sonnet_55_runs_without_up_front_thinking() -> None:
    backend = Backend(
        stream_response(message_start(), *text_block(0, "Ок."), *message_end("end_turn"))
    )
    llm = backend.llm(model="claude-sonnet-5-5", effort="low")
    await llm.turn(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=300
    )
    sent = backend.requests[0]
    assert sent["thinking"] == {"type": "between_tools"}  # the lowest setting; no up-front thinking
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] == 300  # nothing is spent before the first word, no headroom needed


async def test_thinking_blocks_come_back_unmodified_in_the_next_request() -> None:
    backend = Backend(
        stream_response(
            message_start(),
            *thinking_block(0, "SIG-abc"),
            *text_block(1, "Загружаю."),
            *tool_block(2, "toolu_7", "load_skill", '{"name": "original"}'),
            *message_end("tool_use"),
        )
    )
    llm = backend.llm()
    first = await llm.turn(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=100
    )
    assert [b["type"] for b in first.assistant_content] == ["thinking", "text", "tool_use"]
    assert first.assistant_content[0] == {
        "type": "thinking",
        "thinking": "",
        "signature": "SIG-abc",
    }

    history: list[dict[str, Any]] = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": first.assistant_content},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_7", "content": "тело"}],
        },
    ]
    await llm.turn(system="s", messages=history, tools=[], max_tokens=100)
    sent_assistant = backend.requests[1]["messages"][1]["content"]
    assert sent_assistant[0] == {"type": "thinking", "thinking": "", "signature": "SIG-abc"}


async def test_redacted_thinking_blocks_are_kept_too() -> None:
    redacted = {"type": "redacted_thinking", "data": "ENCRYPTED"}
    events = [
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": redacted},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    ]
    backend = Backend(
        stream_response(
            message_start(), *events, *text_block(1, "Привет."), *message_end("end_turn")
        )
    )
    result = await backend.llm().turn(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=50
    )
    assert result.assistant_content == [redacted, {"type": "text", "text": "Привет."}]


async def test_strict_tools_are_flagged_only_when_enabled_and_requested() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    strict = ToolSpec(name="a", description="d", input_schema=schema, strict=True)
    loose = ToolSpec(name="b", description="d", input_schema=schema)
    reply = stream_response(message_start(), *text_block(0, "."), *message_end("end_turn"))

    backend = Backend(reply)
    await backend.llm().turn(
        system="s",
        messages=[{"role": "user", "content": "x"}],
        tools=[strict, loose],
        max_tokens=50,
    )
    flags = [t.get("strict") for t in backend.requests[0]["tools"]]
    assert flags == [True, None]

    backend = Backend(reply)
    await backend.llm(strict_tools=False).turn(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[strict], max_tokens=50
    )
    assert "strict" not in backend.requests[0]["tools"][0]  # kill switch


async def test_refusal_carries_the_policy_category_and_nothing_else() -> None:
    delta = (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": "refusal",
                "stop_sequence": None,
                "stop_details": {
                    "type": "refusal",
                    "category": "general_harms",
                    "explanation": "СЕКРЕТНЫЙ ТЕКСТ",
                },
            },
            "usage": {"output_tokens": 3},
        },
    )
    backend = Backend(
        stream_response(
            message_start(),
            *text_block(0, "Не могу."),
            delta,
            ("message_stop", {"type": "message_stop"}),
        )
    )
    with pytest.raises(ModelRefusal) as info:
        await backend.llm().turn(
            system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=50
        )
    assert info.value.category == "general_harms"
    assert "СЕКРЕТНЫЙ" not in str(info.value)  # the explanation text is never kept


async def test_context_window_overflow_is_an_error() -> None:
    backend = Backend(
        stream_response(
            message_start(), *text_block(0, "..."), *message_end("model_context_window_exceeded")
        )
    )
    with pytest.raises(LLMError, match="Контекст"):
        await backend.llm().turn(
            system="s", messages=[{"role": "user", "content": "x"}], tools=[], max_tokens=50
        )


def message_body(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_9", "type": "message", "role": "assistant", "model": "claude-guard",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }  # fmt: skip


async def test_complete_with_schema_requests_structured_output() -> None:
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    backend = Backend(httpx.Response(200, json=message_body('{"ok": true}')))
    text, _ = await backend.llm().complete(system="s", user="u", max_tokens=100, schema=schema)
    assert text == '{"ok": true}'
    sent = backend.requests[0]
    assert sent["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": schema},
    }
    assert sent["max_tokens"] == 100 + THINKING_HEADROOM


async def test_complete_without_schema_sends_no_format() -> None:
    backend = Backend(httpx.Response(200, json=message_body("текст")))
    await backend.llm(guard_effort="medium").complete(system="s", user="u", max_tokens=10)
    assert backend.requests[0]["output_config"] == {"effort": "medium"}


async def test_structured_reply_cut_off_by_max_tokens_is_an_error_not_text() -> None:
    backend = Backend(httpx.Response(200, json=message_body('{"ok": tr', "max_tokens")))
    with pytest.raises(LLMError, match="max_tokens"):
        await backend.llm().complete(system="s", user="u", max_tokens=10, schema={"type": "object"})


async def test_complete_refusal_raises_model_refusal() -> None:
    backend = Backend(httpx.Response(200, json=message_body("Не могу.", "refusal")))
    with pytest.raises(ModelRefusal):
        await backend.llm().complete(system="s", user="u", max_tokens=10)
