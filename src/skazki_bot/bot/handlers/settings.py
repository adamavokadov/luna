"""Настройки, приватность и удаление данных."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import MenuCb, SettingCb
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.utils import show
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import User
from skazki_bot.domain.enums import TaleLength

router = new_router("settings")


def _length_of(value: str | None) -> TaleLength:
    try:
        return TaleLength(value) if value else TaleLength.NORMAL
    except ValueError:
        return TaleLength.NORMAL


@router.callback_query(MenuCb.filter(F.action == "settings"))
async def cb_settings(callback: CallbackQuery, bot: Bot, state: FSMContext, user: User) -> None:
    await callback.answer()
    await state.clear()
    length = _length_of(user.tale_length)
    await show(callback, bot, texts.settings_text(length), kb.settings_kb(length))


@router.callback_query(SettingCb.filter(F.key == "length"))
async def cb_length(
    callback: CallbackQuery, callback_data: SettingCb, bot: Bot, sf: SessionFactory, user: User
) -> None:
    await callback.answer()
    try:
        length = TaleLength(callback_data.value)
    except ValueError:
        return
    async with sf.begin() as session:
        await repo.set_tale_length(session, user.id, length.value)
    await show(callback, bot, texts.settings_text(length), kb.settings_kb(length))


@router.callback_query(SettingCb.filter(F.key == "privacy"))
async def cb_privacy(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await show(callback, bot, texts.PRIVACY, kb.privacy_kb())


@router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    await message.answer(texts.PRIVACY, reply_markup=kb.back_home_kb())


@router.message(Command("delete"))
async def cmd_delete(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.DELETE_ASK, reply_markup=kb.confirm_delete_data_kb())


@router.callback_query(SettingCb.filter(F.key == "delete_ask"))
async def cb_delete_ask(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await show(callback, bot, texts.DELETE_ASK, kb.confirm_delete_data_kb())


@router.callback_query(SettingCb.filter(F.key == "delete_yes"))
async def cb_delete_yes(
    callback: CallbackQuery, bot: Bot, state: FSMContext, sf: SessionFactory, user: User
) -> None:
    await callback.answer()
    async with sf.begin() as session:
        await repo.delete_user_data(session, user.id)
    await state.clear()
    await show(callback, bot, texts.DELETED)


@router.message(Command("stats"))
async def cmd_stats(message: Message, sf: SessionFactory, settings: Settings, user: User) -> None:
    """Для админов (ADMIN_IDS): форматы, стоимость и качество за неделю — по таблице generation_runs."""
    if user.id not in settings.admin_ids:
        await message.answer(texts.UNKNOWN)
        return
    async with sf() as session:
        stats = await repo.skill_usage_stats(session, datetime.now(UTC) - timedelta(days=7))
    await message.answer(texts.stats_text(stats))
