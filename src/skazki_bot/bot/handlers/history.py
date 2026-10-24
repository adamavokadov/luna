"""Раздел «Мои сказки»: список с пагинацией и повторное чтение."""

from __future__ import annotations

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import MenuCb, ShowTaleCb, TalesPageCb
from skazki_bot.bot.delivery import send_tale
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.handlers.onboarding import begin_create
from skazki_bot.bot.utils import chat_id_of, show
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import User
from skazki_bot.harness import SkillRegistry

router = new_router("history")


async def open_tales(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    skills: SkillRegistry,
    *,
    page: int,
    fresh: bool = False,
) -> None:
    await state.clear()
    async with sf.begin() as session:
        child = await repo.get_active_child(session, user.id)
        if child is None:
            total, items = 0, []
        else:
            total = await repo.count_tales(session, user.id, child.id)
            pages = max((total + kb.TALES_PAGE_SIZE - 1) // kb.TALES_PAGE_SIZE, 1)
            page = min(max(page, 0), pages - 1)
            items = await repo.list_tales(
                session,
                user.id,
                child.id,
                limit=kb.TALES_PAGE_SIZE,
                offset=page * kb.TALES_PAGE_SIZE,
            )
    if child is None:
        await begin_create(callback, bot, state, intro=texts.NEED_PROFILE)
        return
    if total == 0:
        await show(callback, bot, texts.NO_TALES, kb.after_rate_kb(), fresh=fresh)
        return
    await show(
        callback,
        bot,
        texts.tales_list(child, total),
        kb.tales_list_kb(
            items, page=page, total=total, emoji_by_skill={s.name: s.emoji for s in skills.all()}
        ),
        fresh=fresh,
    )


@router.callback_query(MenuCb.filter(F.action == "tales"))
async def cb_tales(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    skills: SkillRegistry,
) -> None:
    await callback.answer()
    await open_tales(callback, bot, state, sf, user, skills, page=0)


@router.callback_query(TalesPageCb.filter())
async def cb_tales_page(
    callback: CallbackQuery,
    callback_data: TalesPageCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    skills: SkillRegistry,
) -> None:
    await callback.answer()
    await open_tales(
        callback, bot, state, sf, user, skills, page=callback_data.page, fresh=callback_data.fresh
    )


@router.callback_query(ShowTaleCb.filter())
async def cb_show_tale(
    callback: CallbackQuery, callback_data: ShowTaleCb, bot: Bot, sf: SessionFactory, user: User
) -> None:
    async with sf.begin() as session:
        tale = await repo.get_tale(session, user.id, callback_data.tale_id)
    if tale is None:
        await callback.answer("Не нашла эту сказку 🤔", show_alert=True)
        return
    await callback.answer()
    await send_tale(
        bot,
        chat_id_of(callback),
        title=tale.title,
        text=tale.text,
        markup=kb.tale_view_kb(callback_data.page),
        parent_note=tale.parent_note,
    )
