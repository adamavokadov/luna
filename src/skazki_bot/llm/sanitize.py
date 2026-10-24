"""Очистка пользовательского ввода перед попаданием в промпт и базу."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_ANGLE = re.compile(r"[<>]")  # не даём «закрыть» наши XML-подобные теги
_SPACES = re.compile(r"\s+")
_NAME = re.compile(r"[^\W\d_]+(?:[ \-'’][^\W\d_]+)*")  # буквы любых алфавитов, дефис, апостроф
_NAME_WORD_START = re.compile(r"(^|[ \-])([^\W\d_])")

MAX_NAME_LEN = 30


def clean_text(value: str, max_len: int) -> str:
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL.sub("", value)
    value = _ANGLE.sub("", value)
    value = _SPACES.sub(" ", value).strip()
    return value[:max_len].rstrip()


def clean_name(value: str) -> str | None:
    """Возвращает аккуратное имя («маша» → «Маша») или None, если ввод не похож на имя."""
    value = _SPACES.sub(" ", unicodedata.normalize("NFC", value)).strip()
    if not value or len(value) > MAX_NAME_LEN or not _NAME.fullmatch(value):
        return None
    return _NAME_WORD_START.sub(lambda m: m.group(1) + m.group(2).upper(), value)
