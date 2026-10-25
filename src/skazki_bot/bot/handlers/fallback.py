"""Последний рубеж: устаревшие кнопки и неожиданные сообщения."""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import smalltalk, texts
from skazki_bot.bot.handlers.base import new_router

router = new_router("fallback")


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    await callback.answer(texts.STALE_BUTTON, show_alert=True)


@router.message()
async def unknown_message(message: Message) -> None:
    reply = smalltalk.reply_to(message.text or "")
    if reply is not None:  # thanks, a greeting, a hard day: Luna answers like a person
        await message.answer(reply.text, reply_markup=reply.markup)
        return
    await message.answer(texts.UNKNOWN, reply_markup=kb.back_home_kb())
