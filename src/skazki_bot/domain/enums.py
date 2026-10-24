from __future__ import annotations

from enum import StrEnum


class Gender(StrEnum):
    BOY = "boy"
    GIRL = "girl"

    @property
    def emoji(self) -> str:
        return "👦" if self is Gender.BOY else "👧"

    @property
    def label(self) -> str:
        return "мальчик" if self is Gender.BOY else "девочка"


class TaleLength(StrEnum):
    SHORT = "short"
    NORMAL = "normal"
    LONG = "long"

    @property
    def label(self) -> str:
        return {"short": "Покороче", "normal": "Обычная", "long": "Подлиннее"}[self.value]


class TaleMode(StrEnum):
    CLASSIC = "classic"  # классический сюжет, адаптированный под ребёнка
    ORIGINAL = "original"  # новая сказка с нуля
