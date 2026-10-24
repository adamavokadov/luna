"""Команды /start, /menu, /help, /cancel и возврат в главное меню."""

from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import MenuCb
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.handlers.onboarding import begin_create
from skazki_bot.bot.utils import show
from skazki_bot.bot.views import main_menu_view
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import User
from skazki_bot.services.tale_service import TaleService

router = new_router("start")


async def open_menu(
    event: Message | CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    tales: TaleService,
    user: User,
    *,
    fresh: bool = False,
    greeting: str = "",
) -> None:
    view = await main_menu_view(sf, tales, user.id)
    if view is None:
        await begin_create(event, bot, state, intro=texts.NEED_PROFILE)
        return
    text, markup = view
    await show(event, bot, greeting + text, markup, fresh=fresh)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    tales: TaleService,
    user: User,
) -> None:
    await state.clear()
    view = await main_menu_view(sf, tales, user.id)
    if view is None:
        await message.answer(texts.WELCOME_NEW)
        await begin_create(message, bot, state)
        return
    text, markup = view
    await message.answer("С возвращением! 🌟\n\n" + text, reply_markup=markup)


@router.message(Command("menu", "cancel"))
async def cmd_menu(
    message: Message,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    tales: TaleService,
    user: User,
) -> None:
    await state.clear()
    await open_menu(message, bot, state, sf, tales, user)


@router.callback_query(MenuCb.filter(F.action == "home"))
async def cb_home(
    callback: CallbackQuery,
    callback_data: MenuCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    tales: TaleService,
    user: User,
) -> None:
    await callback.answer()
    await state.clear()
    await open_menu(callback, bot, state, sf, tales, user, fresh=callback_data.fresh)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)
