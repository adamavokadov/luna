"""Сборка приложения: бот, диспетчер, FSM-хранилище, запуск в режиме polling или webhook."""

from __future__ import annotations

import asyncio
import contextlib
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseEventIsolation, BaseStorage, DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from skazki_bot.bot.handlers import build_router
from skazki_bot.bot.middlewares import ThrottlingMiddleware, UserMiddleware
from skazki_bot.config import Settings
from skazki_bot.db.base import SessionFactory, create_engine, create_session_factory
from skazki_bot.harness import SkillRegistry, TaleHarness
from skazki_bot.llm import build_llm
from skazki_bot.logging import get_logger
from skazki_bot.services.tale_service import TaleService

log = get_logger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать / вернуться"),
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="new", description="Новая сказка"),
    BotCommand(command="profile", description="Профиль ребёнка"),
    BotCommand(command="delete", description="Удалить мои данные"),
    BotCommand(command="help", description="Помощь"),
]
SHORT_DESCRIPTION = "Персональные сказки для вашего ребёнка ✨"
DESCRIPTION = (
    "Я сочиняю сказки с именем вашего малыша, его любимыми героями и в понятном для его возраста "
    "стиле. Расскажите о ребёнке — и вечером будет что почитать 🌙"
)


def build_storage(settings: Settings) -> tuple[BaseStorage, BaseEventIsolation]:
    """Redis — если задан REDIS_URL (состояния переживают рестарты), иначе память процесса."""
    if settings.redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Для REDIS_URL установите extras: uv sync --extra redis") from exc
        storage = RedisStorage.from_url(
            settings.redis_url, key_builder=DefaultKeyBuilder(with_destiny=True)
        )
        return storage, storage.create_isolation()
    return MemoryStorage(), SimpleEventIsolation()


async def on_startup(bot: Bot) -> None:
    await bot.set_my_commands(COMMANDS)
    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_description(DESCRIPTION)
    me = await bot.get_me()
    log.info("bot_started", username=me.username)


def build_dispatcher(
    *,
    settings: Settings,
    sf: SessionFactory,
    tales: TaleService,
    skills: SkillRegistry,
    storage: BaseStorage | None = None,
    isolation: BaseEventIsolation | None = None,
    throttle: bool = True,
) -> Dispatcher:
    # events_isolation: апдейты одного пользователя обрабатываются по очереди —
    # без этого быстрые тапы по кнопкам интересов затирали бы друг друга в FSM-данных.
    dp = Dispatcher(
        storage=storage or MemoryStorage(),
        events_isolation=isolation or SimpleEventIsolation(),
        settings=settings,
        sf=sf,
        tales=tales,
        skills=skills,
    )
    for observer in (dp.message, dp.callback_query):
        if throttle:
            observer.outer_middleware(ThrottlingMiddleware())
        observer.outer_middleware(UserMiddleware())
    dp.include_router(build_router())
    dp.startup.register(on_startup)
    return dp


def build_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def build_web_app(bot: Bot, dp: Dispatcher, *, path: str, secret: str | None) -> web.Application:
    """aiohttp-приложение: вебхук Telegram (с проверкой секретного заголовка) и /healthz."""
    app = web.Application()

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.router.add_get("/healthz", healthz)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=path)
    setup_application(app, dp, bot=bot)
    return app


async def run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    assert settings.webhook_base_url  # гарантируют настройки
    secret = settings.webhook_secret.get_secret_value() if settings.webhook_secret else None
    app = build_web_app(bot, dp, path=settings.webhook_path, secret=secret)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, settings.web_host, settings.web_port).start()
    await bot.set_webhook(
        url=settings.webhook_base_url.rstrip("/") + settings.webhook_path,
        secret_token=secret,
        allowed_updates=dp.resolve_used_update_types(),
    )
    log.info("webhook_started", port=settings.web_port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows
            loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        await runner.cleanup()


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    sf = create_session_factory(engine)
    skills = SkillRegistry.load(settings.skills_dir)
    harness = TaleHarness(llm=build_llm(settings), registry=skills, settings=settings)
    tales = TaleService(sf=sf, harness=harness, settings=settings)
    log.info("skills_loaded", count=len(skills), names=[s.name for s in skills.all()])
    storage, isolation = build_storage(settings)
    bot = build_bot(settings)
    dp = build_dispatcher(
        settings=settings, sf=sf, tales=tales, skills=skills, storage=storage, isolation=isolation
    )
    try:
        if settings.run_mode == "webhook":
            await run_webhook(bot, dp, settings)
        else:
            await run_polling(bot, dp)
    finally:
        await bot.session.close()
        await storage.close()
        await engine.dispose()
