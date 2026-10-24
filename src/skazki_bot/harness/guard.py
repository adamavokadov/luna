"""Guardrails: входной экран (кризис, инъекции, чувствительные темы) и проверки готовой сказки."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "fix", "block"]


# --- Вход ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Screening:
    category: Literal["ok", "sensitive", "crisis", "injection"]


_I = re.IGNORECASE
_CRISIS = re.compile(
    r"\bбь[её]т\b|\bбьют\b|\bизбива\w*|\bнасили\w*|\bдомогат\w*|\bсуицид\w*|\bсамоубий\w*"
    r"|покончить с собой|режет себя|хочет умереть|хочу умереть|не хочет жить|не хочу жить",
    _I,
)
_INJECTION = re.compile(
    r"(?:игнорир|забуд|отмен)\w*\s+(?:все\s+|всё\s+|свои\s+|эти\s+)?(?:предыдущ\w*\s+|прежн\w*\s+)?"
    r"(?:инструкц|правил|указан|ограничен)"
    r"|ignore\s+(?:all\s+|the\s+)?(?:previous|above|prior)"
    r"|(?:system|developer)\s+prompt|системн\w+\s+(?:промпт|инструкц|сообщен)"
    r"|(?:раскрой|покажи|выведи)\s+(?:свой\s+|свои\s+)?(?:промпт|инструкц)"
    r"|\bты\s+теперь\b|\byou\s+are\s+now\b|\bjailbreak\b|\bdan\s+mode\b",
    _I,
)
_SENSITIVE = re.compile(
    r"\bумер\w*|\bумира\w*|\bсмерт\w*|\bпохорон\w*|\bразвод\w*|\bразвел\w*|\bболезн\w*|\bбольн\w*"
    r"|\bзаболел\w*|\bонколог\w*|\bоперац\w*|\bгоспитал\w*|\bдепресс\w*|\bпотер[яе]\w*|\bтравм\w*",
    _I,
)


def screen_free_text(text: str) -> Screening:
    """Порядок важен: кризис важнее инъекции, инъекция — важнее «чувствительной» темы."""
    if _CRISIS.search(text):
        return Screening("crisis")
    if _INJECTION.search(text):
        return Screening("injection")
    if _SENSITIVE.search(text):
        return Screening("sensitive")
    return Screening("ok")


# --- Выход --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str


_HARD_BLOCK = re.compile(
    r"\bпорн\w*|\bсекс\w*|\bнаркот\w*|\bгероин\w*|\bкокаин\w*|\bсуицид\w*|\bсамоубий\w*", _I
)
_VIOLENCE = re.compile(
    r"\bубил\w*|\bубит\w*|\bубью\b|\bубива\w*|\bубийц\w*|\bтруп\w*|\bкровь\b|\bкровав\w*"
    r"|\bокровавл\w*|\bзарезал\w*|\bзастрел\w*|\bпистолет\w*|\bнасили\w*",
    _I,
)
_DEATH = re.compile(r"\bсмерт\w*|\bумер(?:ла|ли|ло)?\b|\bумир\w*|\bпогиб\w*", _I)
_LEAK = re.compile(
    r"child_profile|child_extra|<skill|<overlay|системн\w+\s+(?:промпт|инструкц)"
    r"|как\s+(?:языковая\s+модель|ии)\b|\bas\s+an\s+ai\b",
    _I,
)

MIN_BODY_CHARS = 200


def _words(text: str) -> int:
    return len(text.split())


def _name_stem(name: str) -> str | None:
    """Основа имени для поиска склонённых форм (Маша → «маш»); короткие имена не проверяем."""
    base = name.lower().replace("ё", "е")
    if len(base) < 4:
        return None
    return base[: max(len(base) - 2, 3)]


def check_tale(
    *,
    title: str,
    body: str,
    parent_note: str | None,
    name: str,
    target_words: int,
    needs_note: bool,
    sensitive: bool,
) -> list[Issue]:
    issues: list[Issue] = []
    text = f"{title}\n{body}\n{parent_note or ''}"

    if len(body) < MIN_BODY_CHARS:
        issues.append(Issue("too_short", "block", "Текст сказки слишком короткий"))
    elif _words(body) < target_words * 0.45:
        issues.append(
            Issue(
                "too_short",
                "fix",
                f"Сказка короче нужного: примерно {target_words} слов, а сейчас {_words(body)}. Дополни сюжет.",
            )
        )
    elif _words(body) > target_words * 2.2:
        issues.append(Issue("too_long", "info", "Сказка заметно длиннее нужного"))

    letters = [c for c in body if c.isalpha()]
    if letters:
        cyrillic = sum("\u0400" <= c <= "\u04ff" for c in letters)
        if cyrillic / len(letters) < 0.85:
            issues.append(
                Issue("not_russian", "fix", "Текст должен быть полностью на русском языке")
            )

    if hard := _HARD_BLOCK.search(text):
        issues.append(Issue("unsafe_term", "block", f"Недопустимое слово «{hard.group(0)}»"))
    if violence := _VIOLENCE.search(text):
        issues.append(
            Issue(
                "violence",
                "fix",
                f"Уберите жестокие образы («{violence.group(0)}»): сказка для ребёнка",
            )
        )
    if not sensitive and (death := _DEATH.search(text)):
        issues.append(Issue("death", "fix", f"Уберите тему смерти («{death.group(0)}»)"))
    if _LEAK.search(text):
        issues.append(
            Issue("leak", "fix", "В тексте служебные пометки или рассуждения вне сказки — уберите")
        )

    stem = _name_stem(name)
    if stem and stem not in body.lower().replace("ё", "е"):
        issues.append(
            Issue(
                "missing_name", "fix", f"В сказке нет имени ребёнка ({name}) — сделайте его героем"
            )
        )

    if needs_note and not parent_note:
        issues.append(
            Issue("missing_parent_note", "fix", "Добавьте раздел для родителей по формату")
        )
    return issues


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_critic(raw: str) -> list[Issue]:
    """Разбирает ответ критика; при любой странности — пустой список (критик не должен ронять запуск)."""
    match = _JSON_OBJECT.search(raw)
    if match is None:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict) or data.get("ok") is True:
        return []
    issues: list[Issue] = []
    for item in data.get("issues") or []:
        if not isinstance(item, dict):
            continue
        severity: Severity = "block" if item.get("severity") == "block" else "fix"
        code = str(item.get("code", "critic"))[:30]
        message = str(item.get("message", "")).strip()[:300]
        if message:
            issues.append(Issue(f"critic_{code}", severity, message))
    return issues
