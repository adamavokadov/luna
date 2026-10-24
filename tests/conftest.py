"""Общие фикстуры: диспетчер на настоящих хендлерах, «записывающая» сессия Telegram, FakeLLM, SQLite."""

from __future__ import annotations

import itertools
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.filters.callback_data import CallbackData
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    GetMe,
    SendMessage,
    SendMessageDraft,
    TelegramMethod,
)
from aiogram.methods.base import TelegramType
from aiogram.types import Message, User
from sqlalchemy import select

from skazki_bot.app import build_dispatcher
from skazki_bot.bot import texts
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory, create_engine, create_session_factory
from skazki_bot.db.models import Base, Child, GenerationRun, Tale
from skazki_bot.harness import SkillRegistry, TaleHarness
from skazki_bot.llm.fake import FakeLLM
from skazki_bot.services.tale_service import TaleService


class RecordingSession(BaseSession):
    """Вместо сети запоминает вызовы Bot API и отдаёт правдоподобные ответы."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._ids = itertools.count(1000)

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        self.calls.append(method)
        result: Any = True
        if isinstance(method, SendMessage):
            result = Message.model_validate(
                {
                    "message_id": next(self._ids),
                    "date": 0,
                    "chat": {"id": method.chat_id, "type": "private"},
                    "text": method.text,
                },
                context={"bot": bot},
            )
        elif isinstance(method, GetMe):
            result = User(id=1, is_bot=True, first_name="Bot", username="skazki_test_bot")
        return result  # type: ignore[no-any-return]

    async def stream_content(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[bytes]:  # pragma: no cover
        if False:
            yield b""

    # --- удобные выборки ---
    def sent_texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, SendMessage) and c.text]

    def edited_texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, EditMessageText) and c.text]

    def shown_texts(self) -> list[str]:
        return self.sent_texts() + self.edited_texts()

    def drafts(self) -> list[SendMessageDraft]:
        return [c for c in self.calls if isinstance(c, SendMessageDraft)]

    def alerts(self) -> list[AnswerCallbackQuery]:
        return [c for c in self.calls if isinstance(c, AnswerCallbackQuery) and c.show_alert]


@dataclass
class App:
    dp: Dispatcher
    bot: Bot
    session: RecordingSession
    sf: SessionFactory
    tales: TaleService
    harness: TaleHarness
    skills: SkillRegistry
    settings: Settings


@pytest.fixture(autouse=True)
def _no_part_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skazki_bot.bot.delivery.PART_DELAY", 0)


ADMIN_ID = 99_001


@pytest_asyncio.fixture(scope="session")
async def app(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[App]:
    db_path: Path = tmp_path_factory.mktemp("db") / "test.db"
    settings = Settings(  # type: ignore[call-arg]
        bot_token="123456:TEST",
        llm_provider="fake",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        daily_tale_limit=3,
        draft_min_interval=0.0,
        admin_ids=[ADMIN_ID],
        _env_file=None,
    )
    engine = create_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = create_session_factory(engine)
    skills = SkillRegistry.load()
    harness = TaleHarness(
        llm=FakeLLM(delay=0), registry=skills, settings=settings, rng=random.Random(7)
    )
    tales = TaleService(sf=sf, harness=harness, settings=settings)
    dp = build_dispatcher(settings=settings, sf=sf, tales=tales, skills=skills, throttle=False)
    session = RecordingSession()
    bot = Bot(
        "123456:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    yield App(
        dp=dp,
        bot=bot,
        session=session,
        sf=sf,
        tales=tales,
        harness=harness,
        skills=skills,
        settings=settings,
    )
    await engine.dispose()


_user_ids = itertools.count(10_000)


class Client:
    """Имитация родителя, пишущего боту. Каждый тест получает нового пользователя."""

    def __init__(self, app: App, user_id: int | None = None) -> None:
        self.app = app
        self.user_id = user_id if user_id is not None else next(_user_ids)
        self._update_id = itertools.count(1)
        self._message_id = itertools.count(1)
        app.session.calls.clear()

    @property
    def calls(self) -> RecordingSession:
        return self.app.session

    def _from(self) -> dict[str, Any]:
        return {"id": self.user_id, "is_bot": False, "first_name": "Parent"}

    def _chat(self) -> dict[str, Any]:
        return {"id": self.user_id, "type": "private"}

    async def send(self, text: str) -> None:
        await self.app.dp.feed_raw_update(
            self.app.bot,
            {
                "update_id": next(self._update_id),
                "message": {
                    "message_id": next(self._message_id),
                    "date": 0,
                    "chat": self._chat(),
                    "from": self._from(),
                    "text": text,
                },
            },
        )
        self._assert_no_error()

    async def press(self, data: CallbackData) -> None:
        await self.app.dp.feed_raw_update(
            self.app.bot,
            {
                "update_id": next(self._update_id),
                "callback_query": {
                    "id": str(next(self._update_id)),
                    "from": self._from(),
                    "chat_instance": "ci",
                    "data": data.pack(),
                    "message": {
                        "message_id": next(self._message_id),
                        "date": 0,
                        "chat": self._chat(),
                        "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                        "text": "menu",
                    },
                },
            },
        )
        self._assert_no_error()

    def _assert_no_error(self) -> None:
        assert texts.ERROR not in self.calls.sent_texts(), (
            "Хендлер упал — смотрите лог (captured stdout)"
        )

    def last_markup_data(self) -> list[str]:
        """callback_data всех кнопок последнего показанного сообщения (отправленного или изменённого)."""
        for call in reversed(self.calls.calls):
            if isinstance(call, SendMessage | EditMessageText) and call.reply_markup is not None:
                markup = call.reply_markup
                return [
                    b.callback_data
                    for row in markup.inline_keyboard
                    for b in row
                    if b.callback_data
                ]  # type: ignore[union-attr]
        return []

    # --- доступ к БД ---
    async def child(self) -> Child | None:
        async with self.app.sf.begin() as s:
            return await repo.get_active_child(s, self.user_id)

    async def runs(self) -> list[GenerationRun]:
        async with self.app.sf.begin() as s:
            rows = await s.scalars(
                select(GenerationRun)
                .where(GenerationRun.user_id == self.user_id)
                .order_by(GenerationRun.id)
            )
            return list(rows)

    async def tales(self) -> list[Tale]:
        async with self.app.sf.begin() as s:
            rows = await s.scalars(
                select(Tale).where(Tale.user_id == self.user_id).order_by(Tale.id)
            )
            return list(rows)


@pytest_asyncio.fixture
async def client(app: App) -> Client:
    return Client(app)
