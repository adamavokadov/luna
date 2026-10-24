"""Разбор ответа модели: название, текст, раздел «Для родителей»; подчистка markdown, эмодзи, обрывов."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MD_CHARS = re.compile(r"[*#`]+")
_EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u200d]")
_TITLE_PREFIX = re.compile(r"^\s*(?:название|title)\s*[:\-–—]\s*", re.IGNORECASE)
_PARENT_MARKER = re.compile(
    r"^[ \t]*=+[ \t]*для родителей[ \t]*=+[ \t]*$", re.IGNORECASE | re.MULTILINE
)
_SENTENCE_END = '.!?…»")'
MAX_TITLE_LEN = 80
MAX_NOTE_LEN = 900


@dataclass(frozen=True)
class ParsedTale:
    title: str
    body: str
    parent_note: str | None = None


def trim_incomplete_tail(text: str) -> str:
    """Если ответ оборвался на полуслове (упёрлись в max_tokens) — режем до последнего предложения."""
    text = text.rstrip()
    if not text or text[-1] in _SENTENCE_END:
        return text
    cut = max(text.rfind(ch) for ch in ".!?…")
    return text[: cut + 1] if cut >= int(len(text) * 0.7) else text


def parse_tale(raw: str, fallback_title: str) -> ParsedTale:
    cleaned = _EMOJI.sub("", _MD_CHARS.sub("", raw)).strip()
    if not cleaned:
        return ParsedTale(fallback_title, "")

    note: str | None = None
    marker = _PARENT_MARKER.search(cleaned)
    if marker:
        note = cleaned[marker.end() :].strip()[:MAX_NOTE_LEN] or None
        cleaned = cleaned[: marker.start()].strip()

    first, _, rest = cleaned.partition("\n")
    title = _TITLE_PREFIX.sub("", first).strip().strip("«»\"'").strip()
    body = rest.strip()
    if not body or len(title) > MAX_TITLE_LEN:
        # Модель не отделила заголовок — считаем всё текстом сказки
        return ParsedTale(fallback_title, trim_incomplete_tail(cleaned), note)
    return ParsedTale(title, trim_incomplete_tail(body), note)
