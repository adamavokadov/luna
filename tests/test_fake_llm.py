"""The offline model: its tales must read like tales (no padding loops, no broken Russian cases)."""

from __future__ import annotations

import re

import pytest

from skazki_bot.harness.guard import check_tale
from skazki_bot.llm.fake import FakeLLM
from skazki_bot.llm.parse import parse_tale

# Every word target the bot can ask for: toddler short (220 * 0.6) up to school long (950 * 1.4).
TARGETS = (130, 220, 310, 450, 630, 700, 980, 950, 1330)
# The fake cannot decline names, so a name must never follow a preposition or sit in an oblique case.
AFTER_PREPOSITION = re.compile(r"\b(?:у|про|для|к|о|об|с|без|от|из|на|за|над|под)\s+Рома\b")


def story(target: int, *, girl: bool = False, name: str = "Рома") -> str:
    gender = "девочка" if girl else "мальчик"
    return FakeLLM._story(f"Имя: {name}\nПол: {gender}\nПримерно {target} слов.", "")


@pytest.mark.parametrize("girl", [False, True])
@pytest.mark.parametrize("target", TARGETS)
def test_no_paragraph_is_repeated(target: int, girl: bool) -> None:
    paragraphs = story(target, girl=girl).split("\n\n")
    assert len(paragraphs) == len(set(paragraphs))


@pytest.mark.parametrize("target", TARGETS)
def test_tale_passes_the_deterministic_checks(target: int) -> None:
    parsed = parse_tale(story(target), fallback_title="x")
    issues = check_tale(
        title=parsed.title,
        body=parsed.body,
        parent_note=None,
        name="Рома",
        target_words=target,
        needs_note=False,
        sensitive=False,
    )
    assert [i.code for i in issues] == []


@pytest.mark.parametrize("target", TARGETS)
def test_name_is_always_a_nominative_subject(target: int) -> None:
    text = story(target)
    assert AFTER_PREPOSITION.search(text) is None
    assert re.search(r"\bРома[му]\b|\bРомы\b", text) is None
    assert text.startswith("Рома и добрая звёздочка")


def test_verbs_follow_the_childs_gender() -> None:
    boy, girl = story(1330), story(1330, girl=True, name="Маша")
    assert "Жил-был" in boy and "Жила-была" in girl
    assert "Рома пошёл" in boy and "Маша пошла" in girl
    assert "Рома подошёл" in boy and "Маша подошла" in girl  # the last beats are reached
    assert re.search(r"Маша \w*(?:ёл|ал|ил)\b", girl) is None  # no masculine past tense
    assert re.search(r"Рома \w+(?:ла|ала|ила)\b", boy) is None  # no feminine past tense


def test_a_short_target_gives_a_short_tale() -> None:
    assert len(story(130).split()) < len(story(950).split())
