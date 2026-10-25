"""Luna's persona: soul.md is valid, reaches the system prompt, and the UI speaks in her voice."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest

from skazki_bot import app as app_module
from skazki_bot.bot import texts
from skazki_bot.persona import (
    ACUTE,
    MAX_PROMPT_CHARS,
    MIN_PROMPT_CHARS,
    PersonaError,
    _parse,
    load_persona,
)

# Masculine self-reference or the old anonymous narrator in UI strings
OFF_VOICE = re.compile(r"\bя\s+(?:буду\s+)?(?:рад|готов|уверен)\b|сказочник", re.IGNORECASE)

GOOD = f"""---
name: Луна
name_stressed: "Лу{ACUTE}на"
---
# Notes

<!-- runtime:start -->
{"Ты — Луна, добрая сказочница. " * 15}
<!-- runtime:end -->
"""


def test_persona_is_loaded_from_soul_md() -> None:
    persona = load_persona()
    assert persona.name == "Луна"
    assert persona.name_stressed == f"Лу{ACUTE}на"
    assert MIN_PROMPT_CHARS <= len(persona.prompt) <= MAX_PROMPT_CHARS
    assert "женском роде" in persona.prompt  # she speaks of herself in the feminine
    assert "Лу" in persona.prompt
    letters = [c for c in persona.prompt if c.isalpha()]
    assert sum("\u0400" <= c <= "\u04ff" for c in letters) / len(letters) > 0.9
    assert "Boundaries" in persona.text and "Responsiveness" in persona.text


def test_soul_md_documents_the_voice_rules_the_tests_enforce() -> None:
    text = load_persona().text
    for fragment in ("gender-neutral", "Honesty about being an AI", "opt-in", "No romance"):
        assert fragment.lower() in text.lower(), fragment


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no frontmatter", "frontmatter"),
        (GOOD.replace("name_stressed", "stressed_name"), "name_stressed"),
        (GOOD.replace(f"Лу{ACUTE}на", "Луна2"), "combining acute"),
        (GOOD.replace("<!-- runtime:end -->", ""), "runtime"),
        (GOOD + GOOD.split("---\n", 2)[2], "exactly one"),
        (GOOD.replace("Ты — Луна, добрая сказочница. " * 15, "коротко"), "characters"),
        (GOOD.replace("# Notes", "# Notes").replace("Ты — Луна", "# Ты — Луна", 1), "headings"),
    ],
)
def test_malformed_soul_md_is_rejected(text: str, message: str) -> None:
    with pytest.raises(PersonaError, match=message):
        _parse(text)


def test_well_formed_soul_md_parses() -> None:
    persona = _parse(GOOD)
    assert persona.name == "Луна" and persona.prompt.startswith("Ты — Луна")


# --- The UI speaks in Luna's voice ------------------------------------------------------------------
def ui_strings() -> Iterator[tuple[str, str]]:
    def walk(name: str, value: Any) -> Iterator[tuple[str, str]]:
        if isinstance(value, str):
            yield name, value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from walk(f"{name}[{key}]", item)
        elif isinstance(value, tuple | list):
            for index, item in enumerate(value):
                yield from walk(f"{name}[{index}]", item)

    for attr, value in vars(texts).items():
        if attr.isupper() or attr.startswith("_CHEER"):
            yield from walk(f"texts.{attr}", value)
    for attr in ("DESCRIPTION", "SHORT_DESCRIPTION"):
        yield f"app.{attr}", getattr(app_module, attr)
    for command in app_module.COMMANDS:
        yield f"app.COMMANDS[{command.command}]", command.description


def test_ui_strings_never_use_masculine_self_reference() -> None:
    offenders = {name: text for name, text in ui_strings() if OFF_VOICE.search(text)}
    assert not offenders, offenders


def test_welcome_and_bot_description_introduce_luna_with_the_stress_mark() -> None:
    stressed = load_persona().name_stressed
    assert stressed in texts.WELCOME_NEW
    assert stressed in app_module.DESCRIPTION
    for _, text in ui_strings():  # the stress mark is for introductions only
        if stressed in text:
            continue
        assert ACUTE not in text


def test_failure_and_crisis_messages_use_the_feminine_form() -> None:
    assert "задумалась" in texts.LLM_FAIL
    assert "рада" in texts.CRISIS_SUPPORT


def test_help_lists_the_cheer_command() -> None:
    assert "/cheer" in texts.HELP
    assert any(c.command == "cheer" for c in app_module.COMMANDS)
