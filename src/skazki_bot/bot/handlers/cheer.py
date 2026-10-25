"""Luna's warm words: /cheer on request, the frequency settings and the one-time invitation."""

from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import CheerCb, MenuCb
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.utils import show
from skazki_bot.cheer import CheerService
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import User

router = new_router("cheer")


async def invite_once(bot: Bot, chat_id: int, sf: SessionFactory, user_id: int) -> None:
    """Invite to warm words exactly once per user (the flag flips atomically in the database)."""
    async with sf.begin() as session:
        first_time = await repo.mark_cheer_asked(session, user_id)
    if first_time:
        await bot.send_message(chat_id, texts.CHEER_INVITE, reply_markup=kb.cheer_invite_kb())


@router.message(Command("cheer"))
async def cmd_cheer(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CHEER_ASK_MOOD, reply_markup=kb.cheer_moods_kb())


@router.callback_query(MenuCb.filter(F.action == "cheer"))
@router.callback_query(CheerCb.filter(F.action == "menu"))
async def cb_open(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await show(callback, bot, texts.CHEER_ASK_MOOD, kb.cheer_moods_kb())


@router.callback_query(CheerCb.filter(F.action.in_({"mood", "more"})))
async def cb_word(
    callback: CallbackQuery,
    callback_data: CheerCb,
    bot: Bot,
    cheer: CheerService,
    user: User,
) -> None:
    await callback.answer()
    mood = callback_data.mood
    message = await cheer.prepare(user.id, mood or None)
    await cheer.record_sent(user.id, message.item_id)
    await show(callback, bot, message.html, kb.cheer_after_kb(mood))


@router.callback_query(CheerCb.filter(F.action == "freq_menu"))
async def cb_freq_menu(callback: CallbackQuery, bot: Bot, user: User) -> None:
    await callback.answer()
    await show(
        callback, bot, texts.cheer_freq_text(user.cheer_freq), kb.cheer_freq_kb(user.cheer_freq)
    )


@router.callback_query(CheerCb.filter(F.action == "freq"))
async def cb_freq(
    callback: CallbackQuery,
    callback_data: CheerCb,
    bot: Bot,
    cheer: CheerService,
    user: User,
) -> None:
    await callback.answer()
    freq = callback_data.value
    if not await cheer.set_frequency(user.id, freq):
        return
    if callback_data.src == "settings":  # stay on the picker, now with the new check mark
        await show(callback, bot, texts.cheer_freq_text(freq), kb.cheer_freq_kb(freq))
    else:
        await show(callback, bot, texts.cheer_freq_saved(freq), kb.back_home_kb())
