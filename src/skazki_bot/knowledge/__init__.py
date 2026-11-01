"""Curated knowledge bases bundled with the bot (YAML, validated on load).

* tales/   - classic plots (`classics.yaml`), the folk toolkit (`folk_toolkit.yaml`) and world folk
  plots as raw material for new tales (`world_folk.yaml`);
* cheer/   - compliments, encouragements, proverbs and Luna's framing lines.

Validate everything with `make kb-check` (python -m skazki_bot.knowledge).
"""

from skazki_bot.knowledge.cheer_kb import CheerItem, CheerKB, Kind, Mood, TimeOfDay, load_cheer_kb
from skazki_bot.knowledge.folk_sources import (
    FolkSource,
    FolkSources,
    find_folk_sources,
    folk_source_block,
    load_folk_sources,
)
from skazki_bot.knowledge.tale_kb import FolkToolkit, ToolkitPick, load_folk_toolkit, pick_toolkit

__all__ = [
    "CheerItem",
    "CheerKB",
    "FolkSource",
    "FolkSources",
    "FolkToolkit",
    "Kind",
    "Mood",
    "TimeOfDay",
    "ToolkitPick",
    "find_folk_sources",
    "folk_source_block",
    "load_cheer_kb",
    "load_folk_sources",
    "load_folk_toolkit",
    "pick_toolkit",
]
