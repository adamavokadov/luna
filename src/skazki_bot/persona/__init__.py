"""Luna's persona. `soul.md` is the single source of truth for who she is and how she sounds.

The file mixes developer-facing design notes (English) with one runtime block (Russian) that is
injected into the LLM system prompt. `load_persona()` validates the file so a bad edit fails
`make check` instead of silently degrading the bot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml

_FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n(.*)\Z", re.DOTALL)
_RUNTIME = re.compile(r"<!--\s*runtime:start\s*-->\n?(.*?)\n?<!--\s*runtime:end\s*-->", re.DOTALL)

MIN_PROMPT_CHARS = 300
MAX_PROMPT_CHARS = 1800
ACUTE = "\u0301"  # combining acute accent: marks the stress in «Лу́на»


class PersonaError(ValueError):
    """soul.md is malformed."""


@dataclass(frozen=True)
class Persona:
    name: str  # «Луна»
    name_stressed: str  # «Лу́на» (with a combining acute accent) for the welcome message
    prompt: str  # runtime persona prompt (Russian) for the system prompt
    text: str  # the whole soul.md


def _parse(text: str) -> Persona:
    match = _FRONTMATTER.match(text)
    if match is None:
        raise PersonaError("soul.md must start with YAML frontmatter (--- ... ---)")
    front: Any = yaml.safe_load(match.group(1))
    if not isinstance(front, dict):
        raise PersonaError("soul.md frontmatter must be a mapping")

    name = str(front.get("name", "")).strip()
    stressed = str(front.get("name_stressed", "")).strip()
    if not name or not stressed:
        raise PersonaError("soul.md frontmatter needs `name` and `name_stressed`")
    if ACUTE not in stressed or stressed.replace(ACUTE, "") != name:
        raise PersonaError("`name_stressed` must equal `name` plus a combining acute accent")

    blocks = _RUNTIME.findall(match.group(2))
    if len(blocks) != 1:
        raise PersonaError("soul.md needs exactly one <!-- runtime:start/end --> block")
    prompt = blocks[0].strip()
    if not MIN_PROMPT_CHARS <= len(prompt) <= MAX_PROMPT_CHARS:
        raise PersonaError(
            f"runtime prompt must be {MIN_PROMPT_CHARS}-{MAX_PROMPT_CHARS} characters, "
            f"got {len(prompt)}"
        )
    if "#" in prompt:
        raise PersonaError("runtime prompt must not contain markdown headings")
    return Persona(name=name, name_stressed=stressed, prompt=prompt, text=text)


@lru_cache
def load_persona() -> Persona:
    raw = files("skazki_bot.persona").joinpath("soul.md").read_text(encoding="utf-8")
    return _parse(raw)


__all__ = ["Persona", "PersonaError", "load_persona"]
