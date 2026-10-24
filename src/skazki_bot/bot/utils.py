from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def safe_edit(
    callback: CallbackQuery,
    bot: Bot,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Редактирует сообщение с кнопкой; если нельзя (старое/недоступное) — шлёт новое."""
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
    await bot.send_message(callback.from_user.id, text, reply_markup=markup)


async def show(
    event: Message | CallbackQuery,
    bot: Bot,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    fresh: bool = False,
) -> None:
    """Единая точка вывода: для кнопки правим сообщение (если не fresh), иначе отвечаем новым."""
    if isinstance(event, CallbackQuery):
        if fresh:
            await bot.send_message(chat_id_of(event), text, reply_markup=markup)
        else:
            await safe_edit(event, bot, text, markup)
    else:
        await event.answer(text, reply_markup=markup)


def chat_id_of(event: Message | CallbackQuery) -> int:
    if isinstance(event, CallbackQuery):
        return event.message.chat.id if event.message else event.from_user.id
    return event.chat.id
