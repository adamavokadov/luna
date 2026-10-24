from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.exc import IntegrityError

from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UserMiddleware(BaseMiddleware):
    """Гарантирует, что родитель есть в БД, и кладёт модель User в data["user"]."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        sf: SessionFactory = data["sf"]
        for attempt in (1, 2):
            try:
                async with sf.begin() as session:
                    data["user"] = await repo.upsert_user(session, tg_user.id)
                break
            except IntegrityError:  # два первых апдейта пришли одновременно — повторяем
                if attempt == 2:
                    raise
        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Мягкая защита от спама: лишние события в пределах интервала просто игнорируются."""

    def __init__(self, *, message_interval: float = 0.5, callback_interval: float = 0.2) -> None:
        self._message_interval = message_interval
        self._callback_interval = callback_interval
        self._last: dict[tuple[int, str], float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)
        is_callback = isinstance(event, CallbackQuery)
        key = (tg_user.id, "cb" if is_callback else "msg")
        interval = self._callback_interval if is_callback else self._message_interval
        now = time.monotonic()
        if now - self._last.get(key, 0.0) < interval:
            if isinstance(event, CallbackQuery):
                await event.answer()  # снимаем «часики» на кнопке
            return None
        self._last[key] = now
        if len(self._last) > 10_000:  # простая очистка, чтобы словарь не рос бесконечно
            cutoff = now - 60
            self._last = {k: v for k, v in self._last.items() if v > cutoff}
        return await handler(event, data)
