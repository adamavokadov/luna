"""Shared helpers for reading the YAML knowledge bases bundled with the package."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

import yaml


def read_resource(rel_path: str) -> str:
    """Text of a data file under `skazki_bot/knowledge/` (works from a wheel too)."""
    return files("skazki_bot.knowledge").joinpath(rel_path).read_text(encoding="utf-8")


def load_yaml(rel_path: str) -> Any:
    return yaml.safe_load(read_resource(rel_path))
