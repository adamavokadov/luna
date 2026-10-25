"""Validate every knowledge base, the persona and the cheer skill: `make kb-check`."""

from __future__ import annotations

import sys

from pydantic import ValidationError

from skazki_bot.cheer.skill import CheerSkillError, load_cheer_skill
from skazki_bot.knowledge.cheer_kb import load_cheer_kb
from skazki_bot.knowledge.tale_kb import load_folk_toolkit
from skazki_bot.persona import PersonaError, load_persona
from skazki_bot.stories.library import load_classics


def main() -> int:
    try:
        classics = load_classics()
        toolkit = load_folk_toolkit()
        cheer = load_cheer_kb()
        persona = load_persona()
        skill = load_cheer_skill()
    except (ValidationError, ValueError, PersonaError, CheerSkillError) as exc:
        print(f"✗ knowledge check failed: {exc}")
        return 1
    print(f"✓ tales: {len(classics)} classic plots, {len(toolkit)} folk toolkit entries")
    print(
        f"✓ warm words: {len(cheer.compliments)} compliments, "
        f"{len(cheer.encouragements)} encouragements, {len(cheer.proverbs)} proverbs"
    )
    print(f"✓ persona: {persona.name_stressed}, runtime prompt {len(persona.prompt)} characters")
    print(f"✓ skill: {skill.name} ({skill.meta.emoji} {skill.meta.title})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
