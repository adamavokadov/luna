"""Сборка «экранов» (текст + клавиатура), которые нужны сразу нескольким хендлерам."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.services.tale_service import TaleService

View = tuple[str, InlineKeyboardMarkup]


async def main_menu_view(sf: SessionFactory, tales: TaleService, user_id: int) -> View | None:
    async with sf.begin() as session:
        child = await repo.get_active_child(session, user_id)
    if child is None:
        return None
    remaining = await tales.remaining_today(user_id)
    return texts.menu_text(child, remaining), kb.main_menu()


async def profile_view(sf: SessionFactory, settings: Settings, user_id: int) -> View | None:
    async with sf.begin() as session:
        children = await repo.list_children(session, user_id)
        child = await repo.get_active_child(session, user_id)
    if child is None:
        return None
    total = len(children)
    markup = kb.profile_kb(child, total=total, can_add=total < settings.max_children_per_user)
    return texts.profile_text(child, total), markup
