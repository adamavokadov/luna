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
# The folk toolkit and the folk plot are chosen by the bot, not asked for by the parent: routing
# must not depend on their wording.
_TOOLKIT_BLOCK = re.compile(r"<(folk_toolkit|folk_source)>.*?</\1>", re.DOTALL)
# One continuous arc of distinct beats. The offline model used to cycle five filler lines until the
# word target was met, which printed the same paragraphs again and again. Now every beat is used at
# most once; the story simply ends earlier when the pool runs out. The name is only ever a
# nominative subject (never «у Рома», «про Рома»), because the fake cannot decline names.
_BEATS = (
    "Звёздочка тихонько вздохнула: она сбилась с пути, и теперь не знала, где её место на небе.",
    "— Давай поищем вместе, — предложил{a} {name}. — Вдвоём дорога короче.",
    "Они вышли на тропинку из лунного света, и она тихо засветилась под ногами.",
    "Сначала им встретился старый ёжик с фонариком из светлячка. Он вежливо поклонился и спросил, куда они идут.",
    "— Ищем дом для звёздочки, — объяснил{a} {name}. — Она потерялась.",
    "Ёжик подумал и кивнул.\n— Идите за ручьём, он всегда выводит к тихим местам.",
    "Ручей журчал и переливался, будто напевал колыбельную. Звёздочка слушала и понемногу переставала бояться.",
    "На берегу сидела сонная утка. Она поправила крыло и сказала, что давно хочет спать, да никак не уляжется.",
    "{name} достал{a} из кармана мягкий листок мяты и положил{a} рядом с уткой. Запах был тёплый и успокаивающий.",
    "Утка зевнула, спрятала клюв под крыло и через минуту уже тихонько посапывала.",
    "— Как хорошо, что мы ей помогли, — прошептала звёздочка. — Мне стало чуточку светлее.",
    "Дальше тропинка свернула в яблоневый сад. Яблоки висели низко и пахли мёдом и летом.",
    "Под одной яблоней стоял маленький домик с зелёной дверью. На двери висел колокольчик.",
    "{name} осторожно позвонил{a}, и колокольчик ответил тонким серебряным голосом.",
    "Дверь приоткрылась, и выглянул барсук в вязаном колпаке. Он потёр глаза и улыбнулся.",
    "— Гости в такую позднюю пору — это к чему-то хорошему, — сказал он. — Заходите, чай ещё горячий.",
    "На столе стояли три чашки, плетёная корзинка с сушками и банка малинового варенья.",
    "Звёздочка устроилась на краешке блюдца, и вся кухня наполнилась мягким светом.",
    "Барсук рассказал, что звёзды-потеряшки часто забредают в его сад, и каждый раз всё заканчивается хорошо.",
    "— Главное — не спешить, — добавил он. — Ночь длинная, а небо большое.",
    "После чая барсук достал карту, нарисованную на старом листе лопуха. Линии на ней светились, как жилки.",
    "— Вот здесь вы сейчас, — показал он когтем. — А вот здесь, за холмом, живёт ночная сова.",
    "— Она знает все звёздные дороги, — добавил барсук. — Только говорит медленно, не торопите её.",
    "{name} поблагодарил{a} хозяина, а звёздочка оставила на столе крошечную искорку на память.",
    "Искорка тут же превратилась в светлячка и прочертила над столом маленький светлый круг.",
    "За холмом начиналась поляна, где трава была мягкой, как перина. Роса на ней мерцала, будто рассыпанный бисер.",
    "Здесь пели сверчки. Они стояли рядком, держась лапками за травинки, и тянули одну длинную ласковую песенку.",
    "{name} присел{a} послушать, и звёздочка устроилась на ладони, тёплая, как маленькая печка.",
    "Когда песенка закончилась, сверчки поклонились и показали на старый дуб на краю поляны.",
    "В дупле дуба сидела сова. Огромные глаза её смотрели неспешно и мудро.",
    "— Я вас ждала, — сказала сова так, словно знала всё заранее. — Подойдите ближе.",
    "Звёздочка рассказала про своё небо, про сбившуюся дорогу и про то, как ей стало одиноко.",
    "Сова слушала, не перебивая, а потом расправила крыло и показала на тёмный краешек неба над холмом.",
    "— Видите пустое местечко между двумя звёздами? — спросила она. — Это твоё, малышка.",
    "Звёздочка вгляделась и ахнула: соседки тихонько мигали ей, как будто звали по имени.",
    "— Но подняться на небо можно только по лёгкому ветру, — сказала сова. — А ветер сегодня спит.",
    "{name} подумал{a} и предложил{a} разбудить ветер песенкой. Сверчки охотно согласились помочь.",
    "Все вместе они запели тихо-тихо, так, чтобы ночь ничуть не испугалась. Песенка поплыла над холмом.",
    "И ветер зашевелился, потянулся и открыл один глаз. Потом второй, а потом улыбнулся.",
    "— Что за красивая песня! — прошелестел он. — Кого мне нужно поднять?",
    "— Вот эту звёздочку, — сказал{a} {name}. — Она возвращается домой.",
    "Ветер бережно подхватил звёздочку, как пушинку, и закружил её над поляной.",
    "Звёздочка засмеялась и закричала сверху: — Спасибо вам! Я всё вижу, я лечу!",
    "Она поднималась всё выше, и её свет делался то серебряным, то золотым.",
    "Вот она добралась до пустого местечка между двумя звёздами и встала на своё место.",
    "Соседки обрадовались и тут же подвинулись, чтобы ей было удобно.",
    "Светлая капелька упала с неба и тихо опустилась на ладонь, где недавно сидела звёздочка. Это был подарок на память.",
    "Сова кивнула, ветер ласково подул на прощание, а сверчки запели совсем тихую песенку.",
    "Домой {name} {went} не спеша. Тропинка из лунного света теперь светилась ярче прежнего.",
    "У калитки дремал котёнок. Он приоткрыл один глаз, потянулся и снова положил голову на лапы.",
    "Окошко в доме светилось тёплым светом, будто тоже ждало.",
    "{name} {came} к своей кроватке, и одеяло показалось мягче и уютнее, чем когда-либо.",
    "С неба подмигнула знакомая звёздочка. Теперь у неё было своё место, и она ярко сияла.",
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
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        model: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        return '{"ok": true, "issues": []}', Usage(input_tokens=300, output_tokens=12)

    @staticmethod
    def _story(first_user: str, transcript: str) -> str:
        name_match = re.search(r"^Имя: (.+)$", first_user, re.MULTILINE)
        name = name_match.group(1) if name_match else "малыш"
        girl = "Пол: девочка" in first_user
        forms = {
            "name": name,
            "a": "а" if girl else "",
            "went": "шла" if girl else "шёл",
            "came": "подошла" if girl else "подошёл",
        }
        words_match = re.search(r"Примерно (\d+) слов", first_user)
        target = int(words_match.group(1)) if words_match else 200

        # The name is used only as a nominative subject: the fake cannot decline it.
        paragraphs = [
            f"{name} и добрая звёздочка",
            f"{'Жила-была' if girl else 'Жил-был'} на свете {name}. Однажды вечером {name} "
            f"{'пошла' if girl else 'пошёл'} к окошку и увидел{forms['a']} маленькую звёздочку, "
            "которая никак не могла уснуть.",
            f"— Не спится? — тихонько спросил{forms['a']} {name}.\n— Мне одиноко, — ответила звёздочка.",
            f"Тогда {name} {'нашла' if girl else 'нашёл'} самое мягкое облачко и укрыл{forms['a']} "
            "им звёздочку, как тёплым одеялом.",
        ]
        words = sum(len(p.split()) for p in paragraphs[1:])
        for beat in _BEATS:  # each beat once: a short story beats a looping one
            if words >= target * 0.8:
                break
            paragraph = beat.format(**forms)
            paragraphs.append(paragraph)
            words += len(paragraph.split())
        paragraphs.append(f"И {name} тоже уснул{forms['a']} — крепко-крепко. Спокойной ночи!")
        text = "\n\n".join(paragraphs)
        if "раздел для родителей" in transcript.lower():
            text += (
                "\n\n=== ДЛЯ РОДИТЕЛЕЙ ===\nПосле сказки спросите ребёнка, что ему понравилось больше всего, "
                "и просто выслушайте, не оценивая ответ."
            )
        return text
