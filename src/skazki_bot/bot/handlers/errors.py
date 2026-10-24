from __future__ import annotations

import contextlib

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import ErrorEvent

from skazki_bot.bot import texts
from skazki_bot.logging import get_logger

router = Router(name="errors")
log = get_logger(__name__)


@router.errors()
async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    if isinstance(event.exception, TelegramForbiddenError):
        log.info("user_blocked_bot")  # родитель заблокировал бота — это не ошибка кода
        return True

    log.error("unhandled_error", exc_info=event.exception)
    update = event.update
    chat_id = None
    if update.message is not None:
        chat_id = update.message.chat.id
    elif update.callback_query is not None:
        chat_id = update.callback_query.from_user.id
        with contextlib.suppress(TelegramAPIError):
            await update.callback_query.answer()
    if chat_id is not None:
        with contextlib.suppress(TelegramAPIError):
            await bot.send_message(chat_id, texts.ERROR)
    return True
