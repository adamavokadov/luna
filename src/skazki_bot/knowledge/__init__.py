"""Curated knowledge bases bundled with the bot (YAML, validated on load).

* tales/   - classic plots (`classics.yaml`) and the folk toolkit (`folk_toolkit.yaml`);
* cheer/   - compliments, encouragements, proverbs and Luna's framing lines.

Validate everything with `make kb-check` (python -m skazki_bot.knowledge).
"""

from skazki_bot.knowledge.cheer_kb import CheerItem, CheerKB, Kind, Mood, TimeOfDay, load_cheer_kb
from skazki_bot.knowledge.tale_kb import FolkToolkit, ToolkitPick, load_folk_toolkit, pick_toolkit

__all__ = [
    "CheerItem",
    "CheerKB",
    "FolkToolkit",
    "Kind",
    "Mood",
    "TimeOfDay",
    "ToolkitPick",
    "load_cheer_kb",
    "load_folk_toolkit",
    "pick_toolkit",
]
