from __future__ import annotations

from aiogram import Router

from skazki_bot.bot.handlers import (
    cheer,
    errors,
    fallback,
    history,
    onboarding,
    profile,
    settings,
    start,
    tale,
)


def build_router() -> Router:
    """Порядок важен: команды и анкета раньше всего, fallback — строго последним."""
    root = Router(name="root")
    root.include_routers(
        start.router,
        onboarding.router,
        tale.router,
        profile.router,
        history.router,
        settings.router,
        cheer.router,
        errors.router,
        fallback.router,
    )
    return root
