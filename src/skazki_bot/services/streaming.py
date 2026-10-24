"""Показ хода генерации в чате через sendMessageDraft (Bot API 9.3+; для всех ботов с 9.5).

Черновик — временный «живой» предпросмотр: после отправки настоящего сообщения он исчезает.
Если Telegram отвечает ошибкой (например, клиент/чат не поддерживает) — молча отключаемся,
а пользователь всё равно видит индикатор «печатает…» (ChatActionSender в хендлере).
"""

from __future__ import annotations

import secrets
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from skazki_bot.logging import get_logger

log = get_logger(__name__)

_DRAFT_LIMIT = 4000  # запас до лимита Telegram в 4096 символов


class DraftStreamer:
    def __init__(self, bot: Bot, chat_id: int, *, min_interval: float = 0.9) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._min_interval = min_interval
        self._draft_id = secrets.randbelow(2**31 - 1) + 1  # ненулевой id; один id — одна «анимация»
        self._next_allowed = 0.0
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def push(self, text: str) -> None:
        """Вызывается на каждом чанке; сам троттлит запросы, чтобы не упереться в лимиты."""
        if not self._enabled or not text.strip():
            return
        now = time.monotonic()
        if now < self._next_allowed:
            return
        self._next_allowed = now + self._min_interval
        view = text if len(text) <= _DRAFT_LIMIT else "…" + text[-(_DRAFT_LIMIT - 1) :]
        try:
            # parse_mode=None: у бота по умолчанию HTML, а в «сыром» потоке текста теги не нужны
            await self._bot.send_message_draft(
                chat_id=self._chat_id, draft_id=self._draft_id, text=view, parse_mode=None
            )
        except TelegramRetryAfter as exc:
            self._next_allowed = now + float(exc.retry_after)
        except TelegramAPIError as exc:
            self._enabled = False
            log.info("draft_disabled", chat_id=self._chat_id, reason=type(exc).__name__)
