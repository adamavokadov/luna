"""Отправка готовой сказки в чат: заголовок, разбивка на сообщения, «Для родителей», клавиатура."""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from skazki_bot.bot import texts
from skazki_bot.bot.formatting import split_text
from skazki_bot.bot.texts import q

PART_DELAY = 0.35  # пауза между частями длинной сказки (лимит Telegram ~1 сообщение/сек в чат)


async def send_tale(
    bot: Bot,
    chat_id: int,
    *,
    title: str,
    text: str,
    markup: InlineKeyboardMarkup | None,
    parent_note: str | None = None,
) -> None:
    """Клавиатура уходит на последнее сообщение: «Для родителей», если оно есть, иначе конец сказки."""
    header = f"<b>{q(title)}</b>\n\n"
    parts = split_text(text)
    for index, part in enumerate(parts):
        body = (header if index == 0 else "") + q(part)
        is_last = index == len(parts) - 1
        keyboard = markup if (is_last and not parent_note) else None
        await bot.send_message(chat_id, body, reply_markup=keyboard)
        if not is_last or parent_note:
            await asyncio.sleep(PART_DELAY)
    if parent_note:
        await bot.send_message(chat_id, texts.parent_note(parent_note), reply_markup=markup)
