"""Профили детей: просмотр, правка полей, добавление, переключение, удаление."""

from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import ChildCb, MenuCb
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.handlers.onboarding import EDITABLE_FIELDS, begin_create, begin_edit
from skazki_bot.bot.utils import show
from skazki_bot.bot.views import profile_view
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import User

router = new_router("profile")


async def open_profile(
    event: Message | CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await state.clear()
    view = await profile_view(sf, settings, user.id)
    if view is None:
        await begin_create(event, bot, state, intro=texts.NEED_PROFILE)
        return
    await show(event, bot, *view)


@router.message(Command("profile"))
async def cmd_profile(
    message: Message,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await open_profile(message, bot, state, sf, settings, user)


@router.callback_query(MenuCb.filter(F.action == "profile"))
async def cb_profile(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await callback.answer()
    await open_profile(callback, bot, state, sf, settings, user)


@router.callback_query(ChildCb.filter(F.action == "edit"))
async def cb_edit(
    callback: CallbackQuery,
    callback_data: ChildCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
) -> None:
    await callback.answer()
    if callback_data.field not in EDITABLE_FIELDS:
        return
    async with sf.begin() as session:
        child = await repo.get_child(session, user.id, callback_data.child_id)
    if child is not None:
        await begin_edit(callback, bot, state, child, callback_data.field)


@router.callback_query(ChildCb.filter(F.action == "add"))
async def cb_add(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    async with sf.begin() as session:
        total = await repo.count_children(session, user.id)
    if total >= settings.max_children_per_user:
        await callback.answer(texts.LIMIT_CHILDREN, show_alert=True)
        return
    await callback.answer()
    await begin_create(callback, bot, state)


@router.callback_query(ChildCb.filter(F.action == "switch_list"))
async def cb_switch_list(callback: CallbackQuery, bot: Bot, sf: SessionFactory, user: User) -> None:
    await callback.answer()
    async with sf.begin() as session:
        children = await repo.list_children(session, user.id)
    await show(callback, bot, "🔄 Для кого сочиняем сказки?", kb.switch_child_kb(children))


@router.callback_query(ChildCb.filter(F.action == "switch"))
async def cb_switch(
    callback: CallbackQuery,
    callback_data: ChildCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await callback.answer()
    async with sf.begin() as session:
        await repo.set_active_child(session, user.id, callback_data.child_id)
    await open_profile(callback, bot, state, sf, settings, user)


@router.callback_query(ChildCb.filter(F.action == "del_ask"))
async def cb_delete_ask(
    callback: CallbackQuery, callback_data: ChildCb, bot: Bot, sf: SessionFactory, user: User
) -> None:
    await callback.answer()
    async with sf.begin() as session:
        child = await repo.get_child(session, user.id, callback_data.child_id)
    if child is not None:
        await show(
            callback, bot, texts.confirm_delete_child(child), kb.confirm_delete_child_kb(child.id)
        )


@router.callback_query(ChildCb.filter(F.action == "del_yes"))
async def cb_delete_yes(
    callback: CallbackQuery,
    callback_data: ChildCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    async with sf.begin() as session:
        deleted = await repo.delete_child(session, user.id, callback_data.child_id)
    await callback.answer("Профиль удалён" if deleted else None)
    await open_profile(callback, bot, state, sf, settings, user)
