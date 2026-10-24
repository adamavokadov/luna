from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType


def new_router(name: str) -> Router:
    """Роутер, работающий только в личных чатах (бот — для родителей, не для групп)."""
    router = Router(name=name)
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    return router
