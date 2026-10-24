"""Возрастные профили: насколько сложным, длинным и «страшным» может быть текст."""

from __future__ import annotations

from dataclasses import dataclass

from skazki_bot.domain.enums import TaleLength

MIN_AGE = 2
MAX_AGE = 10


@dataclass(frozen=True)
class AgeProfile:
    key: str
    min_age: int
    max_age: int
    words: int  # базовая длина сказки (слов) для «обычной» длины
    max_scary: int  # допустимый уровень «страшности» сюжета: 0..3
    guidance: str


PROFILES: tuple[AgeProfile, ...] = (
    AgeProfile(
        "toddler",
        2,
        3,
        220,
        1,
        "Очень короткие простые предложения (5–8 слов). Много повторов и ритма, как в потешках. "
        "Звукоподражания (кап-кап, топ-топ). Один-два героя, одно простое действие за раз. "
        "Только бытовые, знакомые малышу слова. Никакой тревоги: всё заканчивается тёплым объятием.",
    ),
    AgeProfile(
        "preschool",
        4,
        5,
        450,
        2,
        "Простые предложения, понятные слова. Лёгкие повторы и диалоги. Сюжет линейный, "
        "с одной маленькой трудностью, которую герои решают добротой или смекалкой. "
        "Немного юмора. Если есть «страшное» — оно скорее смешное и быстро проходит.",
    ),
    AgeProfile(
        "early_school",
        6,
        7,
        700,
        3,
        "Чуть более богатый язык, можно сравнения и несколько сюжетных поворотов. "
        "Герои сомневаются и выбирают, как поступить. Есть тайна или приключение, юмор, "
        "доброе волшебство. Мораль — через поступки героев, а не нравоучение.",
    ),
    AgeProfile(
        "school",
        8,
        10,
        950,
        3,
        "Живой язык, образы, интересные детали и неожиданные повороты. Можно загадку или "
        "небольшое расследование. Герой растёт и делает выбор. Допустима лёгкая интрига, "
        "но без жестокости. Мораль тонкая, без прямых поучений.",
    ),
)

_LENGTH_FACTOR: dict[TaleLength, float] = {
    TaleLength.SHORT: 0.6,
    TaleLength.NORMAL: 1.0,
    TaleLength.LONG: 1.4,
}


def profile_for_age(age: int) -> AgeProfile:
    for profile in PROFILES:
        if profile.min_age <= age <= profile.max_age:
            return profile
    return PROFILES[0] if age < MIN_AGE else PROFILES[-1]


def target_words(age: int, length: TaleLength) -> int:
    return round(profile_for_age(age).words * _LENGTH_FACTOR[length] / 10) * 10
