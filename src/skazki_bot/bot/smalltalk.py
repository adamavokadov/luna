"""Small talk: Luna answers thanks, greetings and a hard day instead of a bare hint.

Deterministic and cheap (regular expressions, no LLM). Crisis wording always wins and gets the
support text, so a distressed message is never met with chit-chat.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.harness.guard import screen_free_text

_FLAGS = re.IGNORECASE
_MOODS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tired", re.compile(r"устал\w*|вымотал\w*|выдохс\w*|нет сил|тяжел\w+ день", _FLAGS)),
    ("anxious", re.compile(r"тревож\w*|тревог\w*|переживаю|беспокоюсь|волнуюсь|страшно", _FLAGS)),
    (
        "stuck",
        re.compile(
            r"не получается|не справляюсь|опускаются руки|ничего не выходит|не знаю,? что делать",
            _FLAGS,
        ),
    ),
)
_THANKS = re.compile(r"\b(?:спасибо|благодарю|спс|благодарствую)\b", _FLAGS)
_GREETING = re.compile(
    r"^\s*(?:привет\w*|здравствуй\w*|добрый\s+(?:день|вечер)|доброе\s+утро|доброй\s+ночи|хай|hello|hi)\b",
    _FLAGS,
)


@dataclass(frozen=True)
class Reply:
    text: str
    markup: InlineKeyboardMarkup


def classify(text: str) -> str | None:
    """crisis | tired | anxious | stuck | thanks | greeting | None."""
    normalized = text.replace("ё", "е").replace("Ё", "Е")
    if screen_free_text(normalized).category == "crisis":
        return "crisis"
    for mood, pattern in _MOODS:
        if pattern.search(normalized):
            return mood
    if _THANKS.search(normalized):
        return "thanks"
    if _GREETING.match(normalized):
        return "greeting"
    return None


def reply_to(text: str, rng: random.Random | None = None) -> Reply | None:
    """Luna's answer to a free-text message outside any dialog, or None if it is not small talk."""
    rng = rng or random.Random()
    intent = classify(text)
    if intent is None:
        return None
    if intent == "crisis":
        return Reply(texts.CRISIS_SUPPORT, kb.back_home_kb())
    if intent == "thanks":
        return Reply(rng.choice(texts.SMALLTALK_THANKS), kb.back_home_kb())
    if intent == "greeting":
        return Reply(rng.choice(texts.SMALLTALK_GREETING), kb.back_home_kb())
    return Reply(texts.SMALLTALK_MOOD[intent], kb.cheer_offer_kb(intent))
