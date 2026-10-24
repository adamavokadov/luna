"""Каталог интересов для кнопок. Каждый интерес связан с темами сюжетов (см. classics.yaml)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interest:
    key: str
    emoji: str
    label: str
    themes: tuple[str, ...]

    @property
    def button(self) -> str:
        return f"{self.emoji} {self.label}"


INTERESTS: tuple[Interest, ...] = (
    Interest("animals", "🐾", "Животные", ("animals", "forest", "farm")),
    Interest("dinosaurs", "🦖", "Динозавры", ("dinosaurs", "adventure")),
    Interest("space", "🚀", "Космос", ("space", "adventure")),
    Interest("cars", "🚗", "Машины и техника", ("transport", "technology")),
    Interest("robots", "🤖", "Роботы", ("technology", "space")),
    Interest("princesses", "👑", "Принцессы и принцы", ("kingdom", "magic")),
    Interest("knights", "🛡️", "Рыцари и драконы", ("kingdom", "adventure", "dragons")),
    Interest("magic", "🪄", "Волшебство", ("magic", "fairies")),
    Interest("sea", "🌊", "Море и рыбки", ("sea", "adventure")),
    Interest("pirates", "🏴‍☠️", "Пираты и клады", ("sea", "adventure")),
    Interest("sport", "⚽", "Футбол и спорт", ("sport", "friendship")),
    Interest("music", "🎵", "Музыка", ("music", "art")),
    Interest("drawing", "🎨", "Рисование", ("art", "magic")),
    Interest("cooking", "🍪", "Вкусняшки и готовка", ("food", "home")),
    Interest("winter", "❄️", "Зима и снег", ("winter", "magic")),
    Interest("insects", "🐞", "Жучки и бабочки", ("insects", "nature", "forest")),
)

BY_KEY: dict[str, Interest] = {i.key: i for i in INTERESTS}


def labels_for(keys: list[str]) -> list[str]:
    return [BY_KEY[k].label for k in keys if k in BY_KEY]


def buttons_for(keys: list[str]) -> list[str]:
    return [BY_KEY[k].button for k in keys if k in BY_KEY]


def themes_for(keys: list[str]) -> set[str]:
    return {theme for k in keys if k in BY_KEY for theme in BY_KEY[k].themes}
