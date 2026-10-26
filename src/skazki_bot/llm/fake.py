"""Детерминированная «модель» для разработки и тестов: без ключа, но с настоящим поведением агента —
маршрутизирует навыки через load_skill, пишет сказку нужного объёма, добавляет раздел для родителей."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Any

from skazki_bot.llm.base import Message, TextCallback, ToolCall, ToolSpec, TurnResult, Usage

_ROUTE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"бо[ия]тся|страх|ссор|ревн|садик|стесня", re.IGNORECASE), "metaphorical"),
    (re.compile(r"стих|рифм", re.IGNORECASE), "rhyme"),
    (re.compile(r"день рождения|праздник", re.IGNORECASE), "celebration"),
)
# The folk toolkit is random decoration appended to the request; routing must not depend on it.
_TOOLKIT_BLOCK = re.compile(r"<folk_toolkit>.*?</folk_toolkit>", re.DOTALL)
_FILLER = (
    "Вокруг было тихо и тепло, а над головой мягко светили звёзды.",
    "По дороге {name} встретил{a} доброго друга, и они пошли дальше вместе.",
    "Ветер шепнул что-то ласковое, и на сердце у {name} стало спокойно.",
    "Они нашли маленький тёплый огонёк, и стало совсем уютно.",
    "Друзья разделили ужин, и всем хватило, потому что делились они от души.",
)


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif block.get("type") == "tool_result":
            parts.append(_text_of(block.get("content", "")))
    return "\n".join(parts)


class FakeLLM:
    def __init__(self, *, delay: float = 0.03, chunk_size: int = 45) -> None:
        self._delay = delay
        self._chunk = chunk_size

    async def turn(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_tokens: int,
        on_text: TextCallback | None = None,
    ) -> TurnResult:
        transcript = "\n".join(_text_of(m["content"]) for m in messages)
        first_user = _text_of(messages[0]["content"])
        used_tools = any(
            isinstance(m["content"], list)
            and any(b.get("type") == "tool_result" for b in m["content"])
            for m in messages
        )

        if "load_skill" in {t.name for t in tools} and not used_tools:
            request = _TOOLKIT_BLOCK.sub("", first_user)
            skill = next((s for rule, s in _ROUTE_RULES if rule.search(request)), "original")
            call = ToolCall(id="fake_tool_1", name="load_skill", input={"name": skill})
            return TurnResult(
                text="",
                tool_calls=(call,),
                assistant_content=[
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=400, output_tokens=20),
            )

        text = self._story(first_user, transcript)
        for i in range(0, len(text), self._chunk):
            if self._delay:
                await asyncio.sleep(self._delay)
            if on_text is not None:
                await on_text(text[i : i + self._chunk])
        return TurnResult(
            text=text,
            tool_calls=(),
            assistant_content=[{"type": "text", "text": text}],
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=600, output_tokens=max(len(text) // 4, 1), cache_read_tokens=300
            ),
        )

    async def complete(
        self, *, system: str, user: str, max_tokens: int, model: str | None = None
    ) -> tuple[str, Usage]:
        return '{"ok": true, "issues": []}', Usage(input_tokens=300, output_tokens=12)

    @staticmethod
    def _story(first_user: str, transcript: str) -> str:
        name_match = re.search(r"^Имя: (.+)$", first_user, re.MULTILINE)
        name = name_match.group(1) if name_match else "малыш"
        girl = "Пол: девочка" in first_user
        a = "а" if girl else ""
        words_match = re.search(r"Примерно (\d+) слов", first_user)
        target = int(words_match.group(1)) if words_match else 200

        paragraphs = [
            f"Сказка про {name} и добрую звёздочку",
            f"Жил-был на свете {name}. Однажды вечером {name} {'пошла' if girl else 'пошёл'} к окошку "
            f"и увидел{a} маленькую звёздочку, которая никак не могла уснуть.",
            f"— Не спится? — тихонько спросил{a} {name}.\n— Мне одиноко, — ответила звёздочка.",
            f"Тогда {name} {'нашла' if girl else 'нашёл'} самое мягкое облачко и укрыл{a} им звёздочку, "
            f"как тёплым одеялом.",
        ]
        words = sum(len(p.split()) for p in paragraphs[1:])
        i = 0
        while words < target * 0.8:
            filler = _FILLER[i % len(_FILLER)].format(name=name, a=a)
            paragraphs.append(filler)
            words += len(filler.split())
            i += 1
        paragraphs.append(f"И {name} тоже уснул{a} — крепко-крепко. Спокойной ночи!")
        text = "\n\n".join(paragraphs)
        if "раздел для родителей" in transcript.lower():
            text += (
                "\n\n=== ДЛЯ РОДИТЕЛЕЙ ===\nПосле сказки спросите ребёнка, что ему понравилось больше всего, "
                "и просто выслушайте, не оценивая ответ."
            )
        return text
