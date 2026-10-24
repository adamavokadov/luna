from __future__ import annotations

import re

_PARAGRAPHS = re.compile(r"\n{2,}")
_SENTENCES = re.compile(r"(?<=[.!?…])\s+")


def _break_long(paragraph: str, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCES.split(paragraph):
        while len(sentence) > limit:  # предложение длиннее лимита — режем жёстко
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, limit: int = 3400) -> list[str]:
    """Делит длинный текст на части по абзацам (лимит Telegram — 4096 символов на сообщение)."""
    parts: list[str] = []
    current = ""
    for paragraph in _PARAGRAPHS.split(text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for piece in _break_long(paragraph, limit):
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    parts.append(current)
                current = piece
    if current:
        parts.append(current)
    return parts
