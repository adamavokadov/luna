"""Тестовые двойники LLM: сценарные «ходы» модели и генератор правдоподобных сказок."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Sequence
from typing import Any

from skazki_bot.llm.base import Message, TextCallback, ToolCall, ToolSpec, TurnResult, Usage


def text_turn(text: str, usage: Usage | None = None) -> TurnResult:
    return TurnResult(
        text=text,
        tool_calls=(),
        assistant_content=[{"type": "text", "text": text}],
        stop_reason="end_turn",
        usage=usage or Usage(input_tokens=100, output_tokens=50),
    )


def tool_turn(
    name: str,
    args: dict[str, Any],
    call_id: str = "tool_1",
    text: str = "",
    usage: Usage | None = None,
) -> TurnResult:
    content: list[dict[str, Any]] = [
        {"type": "tool_use", "id": call_id, "name": name, "input": args}
    ]
    if text:
        content.insert(0, {"type": "text", "text": text})
    return TurnResult(
        text=text,
        tool_calls=(ToolCall(id=call_id, name=name, input=args),),
        assistant_content=content,
        stop_reason="tool_use",
        usage=usage or Usage(input_tokens=80, output_tokens=10),
    )


# Nine words each, so word counts stay predictable. Paragraphs take different windows of this pool,
# so a generated tale never repeats a paragraph (the guard flags looping tales).
_STORY_LINES = (
    "{name} шла по тёплой тропинке и улыбалась ласковому ветру.",
    "Над полем поднималась круглая луна и светила совсем тихо.",
    "Рядом бежал ручей и напевал свою негромкую ночную песенку.",
    "В траве сверчки играли на своих маленьких серебряных скрипках.",
    "Старая яблоня протянула ветку и угостила путников сладким яблоком.",
    "Облачко прилегло на холм и укрыло его мягким пухом.",
    "Лёгкий ветерок подхватил листочек и закружил его над тропинкой.",
    "Далеко за лесом тихо засветилось тёплое окошко маленького домика.",
    "Весёлая белка помахала хвостом и показала верную дорогу дальше.",
    "Сонный ёжик вздохнул и пожелал всем доброй спокойной ночи.",
    "Звёзды мигали друг другу и тихонько переговаривались между собой.",
    "Тёплый свет фонарика ложился на дорожку золотым мягким ковриком.",
    "Маленький мостик через тихий ручей скрипнул и ласково покачнулся.",
    "Пахло мятой, мёдом и свежим хлебом из ближней деревни.",
    "Дорога плавно свернула к речке и спустилась к берегу.",
    "Лягушата на листьях кувшинок затянули свою тихую вечернюю песенку.",
    "Мудрая сова моргнула и сказала, что всё идёт хорошо.",
    "Лунная дорожка на тёмной тихой воде блестела мягким серебром.",
    "Бабочка села на плечо и тихонько сложила светлые крылья.",
    "Трава шептала сказку, а цветы согласно кивали в такт.",
    "Усталые облака медленно плыли домой и зевали на ходу.",
    "Где-то вдалеке запел соловей, и вся ночь затихла, слушая.",
    "Тропинка привела к калитке с резным деревянным петушком наверху.",
    "Все вокруг дышали ровно и спокойно, готовясь ко сну.",
)


def make_story(
    name: str = "Маша", words: int = 300, *, note: str | None = None, title: str = "Звёздный путь"
) -> str:
    """Сказка нужной длины с именем героя — проходит детерминированные проверки guard-слоя."""
    per = 9  # words in one line of the pool
    count = max(words // (per * 3), 1)
    paragraphs = [
        " ".join(_STORY_LINES[(i * 5 + k) % len(_STORY_LINES)].format(name=name) for k in range(3))
        for i in range(count)
    ]
    text = f"{title}\n\n" + "\n\n".join(paragraphs)
    if note:
        text += f"\n\n=== ДЛЯ РОДИТЕЛЕЙ ===\n{note}"
    return text


class ScriptedChat:
    """Выдаёт заранее заданные ходы модели; последний ход повторяется, если сценарий закончился."""

    def __init__(
        self,
        turns: Sequence[TurnResult | Exception],
        *,
        critic: Sequence[str | Exception] = (),
        gate: asyncio.Event | None = None,
    ) -> None:
        self._turns = list(turns)
        self._critic = list(critic)
        self._gate = gate
        self.calls: list[dict[str, Any]] = []
        self.complete_calls: list[dict[str, Any]] = []

    async def turn(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_tokens: int,
        on_text: TextCallback | None = None,
    ) -> TurnResult:
        self.calls.append(
            {
                "system": system,
                "messages": copy.deepcopy(list(messages)),
                "tools": [t.name for t in tools],
                "max_tokens": max_tokens,
            }
        )
        if self._gate is not None:
            await self._gate.wait()
        item = self._turns.pop(0) if len(self._turns) > 1 else self._turns[0]
        if isinstance(item, Exception):
            raise item
        if on_text is not None and item.text:
            await on_text(item.text)
        return item

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        model: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        self.complete_calls.append(
            {"system": system, "user": user, "model": model, "schema": schema}
        )
        raw = self._critic.pop(0) if self._critic else '{"ok": true, "issues": []}'
        if isinstance(raw, Exception):
            raise raw
        return raw, Usage(input_tokens=60, output_tokens=8)
