"""Luna's warm words: skill file, schedule rules, composition, delivery and the bot flows."""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.methods.base import TelegramType
from pydantic import ValidationError

from skazki_bot.bot import smalltalk, texts
from skazki_bot.bot.callbacks import CheerCb, MenuCb
from skazki_bot.bot.handlers.cheer import invite_once
from skazki_bot.cheer import CheerService, compose, is_due, load_cheer_skill
from skazki_bot.cheer.compose import MOODS
from skazki_bot.cheer.schedule import daypart, personal_hour
from skazki_bot.cheer.scheduler import CheerScheduler
from skazki_bot.cheer.skill import CheerSkillError, parse_cheer_skill
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory, create_engine, create_session_factory
from skazki_bot.db.models import Base, User
from skazki_bot.knowledge import load_cheer_kb
from tests.conftest import App, Client, RecordingSession
from tests.test_bot_flow import onboard

TZ = ZoneInfo("Europe/Moscow")
KB = load_cheer_kb()
SKILL = load_cheer_skill()
GAPS = SKILL.gaps()
# 2026-10-26 12:00 UTC is 15:00 in Moscow: inside the 10-21 window
NOON = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def due(
    user_id: int, freq: str = "daily", *, now: datetime = NOON, last: datetime | None = None
) -> bool:
    return is_due(
        now=now,
        tz=TZ,
        user_id=user_id,
        freq=freq,
        last_at=last,
        window_start=10,
        window_end=21,
        gaps=GAPS,
    )


# --- The skill file -------------------------------------------------------------------------------------
def test_builtin_skill_is_valid() -> None:
    assert SKILL.name == "cheer" and SKILL.meta.emoji == "💛"
    assert set(GAPS) == {"daily", "few", "weekly"}
    assert GAPS["daily"] < GAPS["few"] < GAPS["weekly"]
    assert SKILL.meta.recent_memory >= 20
    assert "вы" in SKILL.body and "{child}" in SKILL.body


def test_skill_is_not_a_tale_format() -> None:
    from skazki_bot.harness import SkillRegistry

    assert SkillRegistry.load().get("cheer") is None  # never offered to the tale model


GOOD_SKILL = """---
name: cheer
description: "Тёплые слова."
metadata:
  title: "Тёплые слова"
---
Методика.
"""


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Методика без frontmatter", "frontmatter"),
        (GOOD_SKILL.replace("name: cheer", "name: other"), "name must be"),
        (GOOD_SKILL.replace("description:", "color: red\ndescription:"), "outside the spec"),
        (GOOD_SKILL.replace('description: "Тёплые слова."', 'description: ""'), "description"),
        (GOOD_SKILL.replace("title:", "gap-daily-h: '50'\n  gap-few-h: '40'\n  title:"), "gaps"),
        (GOOD_SKILL.replace("Методика.\n", ""), "body"),
        (GOOD_SKILL.replace('metadata:\n  title: "Тёплые слова"', "metadata: oops"), "mapping"),
    ],
)
def test_malformed_skill_is_rejected(text: str, message: str) -> None:
    with pytest.raises(CheerSkillError, match=message):
        parse_cheer_skill(text)


def test_skill_accepts_a_custom_copy(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(GOOD_SKILL.replace("title:", "gap-weekly-h: '100'\n  title:"), encoding="utf-8")
    assert load_cheer_skill(path).meta.gap_weekly_h == 100


# --- Schedule rules -----------------------------------------------------------------------------------------
def test_dayparts() -> None:
    assert [daypart(h) for h in (4, 5, 10, 11, 16, 17, 23, 0)] == [
        "evening", "morning", "morning", "day", "day", "evening", "evening", "evening",
    ]  # fmt: skip


def test_personal_hour_stays_inside_the_window_and_spreads_users() -> None:
    hours = {personal_hour(uid, 10, 21) for uid in range(1000, 1200)}
    assert hours == set(range(10, 21))
    assert personal_hour(1, 9, 10) == 9  # one-hour window


def test_is_due_rules() -> None:
    assert due(16)  # personal hour 15, local time 15:00
    assert not due(17)  # personal hour 16: not yet
    assert not due(11, "off") and not due(11, "never")
    night = datetime(2026, 10, 26, 0, 30, tzinfo=UTC)  # 03:30 Moscow
    assert not due(11, now=night)
    late = datetime(2026, 10, 26, 18, 30, tzinfo=UTC)  # 21:30 Moscow: window closed
    assert not due(11, now=late)
    catch_up = datetime(2026, 10, 26, 16, 0, tzinfo=UTC)  # 19:00: still in the window
    assert due(11, now=catch_up)  # bot was down at the personal hour 10: catches up

    recent = NOON - GAPS["daily"] + timedelta(minutes=1)
    assert not due(16, last=recent)
    assert due(16, last=NOON - GAPS["daily"])
    assert not due(16, "weekly", last=NOON - timedelta(days=3))
    assert due(16, "weekly", last=NOON - GAPS["weekly"])
    assert not due(16, "few", last=NOON - timedelta(hours=30))
    assert due(16, "few", last=NOON - timedelta(hours=47))


# --- Composition ------------------------------------------------------------------------------------------------
def messages(count: int = 300, **kwargs: Any) -> list[Any]:
    return [compose(KB, rng=random.Random(seed), **kwargs) for seed in range(count)]


def item_of(message: Any) -> Any:
    for kind in ("compliment", "encouragement", "proverb"):
        for item in KB.items(kind):
            if item.id == message.item_id:
                return item
    raise AssertionError(message.item_id)


def test_compose_is_deterministic_for_a_seed() -> None:
    first = compose(KB, local_hour=15, rng=random.Random(4))
    assert first == compose(KB, local_hour=15, rng=random.Random(4))
    assert first.kind in {"compliment", "encouragement", "proverb"}


def test_proactive_messages_use_only_neutral_items() -> None:
    for message in messages(local_hour=14):
        assert "any" in item_of(message).moods


@pytest.mark.parametrize("mood", MOODS)
def test_mood_requests_get_matching_or_neutral_items(mood: str) -> None:
    seen_exact = False
    for message in messages(local_hour=14, mood=mood):
        moods = item_of(message).moods
        assert mood in moods or "any" in moods
        seen_exact = seen_exact or mood in moods
    assert seen_exact


def test_time_of_day_is_respected() -> None:
    for message in messages(local_hour=8):  # morning
        assert {"any", "morning"} & set(item_of(message).times)
    for message in messages(local_hour=20):  # evening
        assert {"any", "evening"} & set(item_of(message).times)


def test_child_items_need_a_name_and_the_name_is_escaped() -> None:
    for message in messages(local_hour=14):
        assert not item_of(message).child
    named = messages(600, local_hour=14, child_name="<b>Маша</b>")
    with_child = [m for m in named if item_of(m).child]
    assert with_child, "child items are used when a name is known"
    for message in with_child:
        assert "&lt;b&gt;Маша&lt;/b&gt;" in message.html and "<b>" not in message.html
        assert "{child}" not in message.html


def test_recent_items_are_not_repeated_until_the_pool_runs_out() -> None:
    first = compose(KB, local_hour=14, rng=random.Random(1))
    for seed in range(100):
        again = compose(KB, local_hour=14, recent=[first.item_id], rng=random.Random(seed))
        assert again.item_id != first.item_id

    everything = [i.id for k in ("compliment", "encouragement", "proverb") for i in KB.items(k)]  # type: ignore[arg-type]
    exhausted = compose(KB, local_hour=14, recent=everything, rng=random.Random(1))
    assert exhausted.item_id  # degrades gracefully instead of failing


def test_the_same_kind_is_less_likely_twice_in_a_row() -> None:
    plain = sum(m.kind == "compliment" for m in messages(local_hour=14)) / 300
    after = (
        sum(
            compose(KB, local_hour=14, recent=["cm01"], rng=random.Random(s)).kind == "compliment"
            for s in range(300)
        )
        / 300
    )
    assert after < plain and after < 0.25


def test_message_layout_and_markup() -> None:
    for message in messages(local_hour=13, mood="stuck"):
        parts = message.html.split("\n\n")
        assert len(parts) == 3, message.html
        assert parts[0] in KB.frames.mood_openers["stuck"]
        assert parts[2] in KB.frames.closers["day"]
        stripped = re.sub(r"</?i>", "", message.html)
        assert "<" not in stripped and ">" not in stripped
        if message.kind == "proverb":
            assert "<i>«" in parts[1] and "»</i>" in parts[1]


# --- Service and scheduler against a real database -------------------------------------------------------------
class ScriptedSession(RecordingSession):
    """Recording session that fails sends on cue (blocked bot, flood control)."""

    def __init__(self, *, fail_with: list[Exception] | None = None) -> None:
        super().__init__()
        self._fail_with = list(fail_with or [])

    async def make_request(
        self, bot: Bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        if isinstance(method, SendMessage) and self._fail_with:
            raise self._fail_with.pop(0)
        return await super().make_request(bot, method, timeout)


def forbidden() -> TelegramForbiddenError:
    return TelegramForbiddenError(
        method=SendMessage(chat_id=1, text="x"), message="Forbidden: bot was blocked by the user"
    )


def retry_after() -> TelegramRetryAfter:
    return TelegramRetryAfter(
        method=SendMessage(chat_id=1, text="x"), message="Too Many Requests", retry_after=0
    )


class Env:
    def __init__(self, sf: SessionFactory, settings: Settings) -> None:
        self.sf = sf
        self.settings = settings
        self.service = CheerService(sf=sf, settings=settings, rng=random.Random(11))

    def scheduler(self, session: RecordingSession) -> CheerScheduler:
        bot = Bot(
            "123456:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        return CheerScheduler(self.service, bot, tick_s=0.01, send_delay_s=0)

    async def add_user(
        self,
        user_id: int,
        freq: str = "daily",
        *,
        child: str | None = None,
        last: datetime | None = None,
    ) -> None:
        async with self.sf.begin() as session:
            await repo.upsert_user(session, user_id)
            await repo.set_cheer_freq(session, user_id, freq)
            if last is not None:
                user = await session.get(User, user_id)
                assert user is not None
                user.cheer_last_at = last
            if child:
                await repo.create_child(
                    session,
                    user_id,
                    name=child,
                    gender="girl",
                    age=5,
                    interests=[],
                    extra_interests="",
                )

    async def user(self, user_id: int) -> User:
        async with self.sf() as session:
            user = await session.get(User, user_id)
            assert user is not None
            return user


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    settings = Settings(  # type: ignore[call-arg]
        bot_token="123456:TEST",
        llm_provider="fake",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'cheer.db'}",
        _env_file=None,
    )
    engine = create_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield Env(create_session_factory(engine), settings)
    await engine.dispose()


async def test_new_users_have_warm_words_off_and_are_never_due(env: Env) -> None:
    async with env.sf.begin() as session:
        user = await repo.upsert_user(session, 16)
    assert user.cheer_freq == "off" and user.cheer_asked is False and user.cheer_recent is None
    assert await env.service.claim_due(NOON) == []


async def test_claim_due_picks_only_users_whose_turn_it_is(env: Env) -> None:
    await env.add_user(16)  # personal hour 15 -> due at 15:00
    await env.add_user(17)  # personal hour 16 -> not yet
    await env.add_user(27, "off")
    await env.add_user(38, "weekly", last=NOON - timedelta(days=2))  # hour 15, but too soon
    assert await env.service.claim_due(NOON) == [16]
    assert await env.service.claim_due(NOON) == []  # the slot is already claimed
    assert (await env.user(16)).cheer_last_at == NOON


async def test_two_replicas_never_double_send(env: Env) -> None:
    await env.add_user(16)
    first, second = await asyncio.gather(env.service.claim_due(NOON), env.service.claim_due(NOON))
    assert sorted(first + second) == [16]


async def test_batch_size_limits_one_pass(env: Env) -> None:
    env.settings.cheer_batch_size = 2
    for uid in (16, 27, 38, 49):  # all have personal hour 15
        await env.add_user(uid)
    assert len(await env.service.claim_due(NOON)) == 2
    assert len(await env.service.claim_due(NOON)) == 2  # the rest on the next pass


async def test_master_switch_stops_everything(env: Env) -> None:
    await env.add_user(16)
    env.settings.cheer_enabled = False
    assert await env.service.claim_due(NOON) == []


async def test_set_frequency_validates(env: Env) -> None:
    await env.add_user(16, "off")
    assert await env.service.set_frequency(16, "weekly") is True
    assert (await env.user(16)).cheer_freq == "weekly"
    assert await env.service.set_frequency(16, "hourly") is False
    assert (await env.user(16)).cheer_freq == "weekly"
    await env.service.disable(16)
    assert (await env.user(16)).cheer_freq == "off"


async def test_scheduler_sends_a_personal_message_with_a_way_out(env: Env) -> None:
    await env.add_user(16, child="Соня")
    session = ScriptedSession()
    sent = await env.scheduler(session).run_once(NOON)

    assert sent == 1
    (call,) = [c for c in session.calls if isinstance(c, SendMessage)]
    assert call.chat_id == 16
    assert call.text and call.text.split("\n\n")[0] in KB.frames.openers["day"]
    buttons = [b.callback_data for row in call.reply_markup.inline_keyboard for b in row]  # type: ignore[union-attr]
    assert CheerCb(action="freq", value="off", src="msg").pack() in buttons
    user = await env.user(16)
    assert user.cheer_recent and len(user.cheer_recent) == 1


async def test_history_prevents_repeats_and_is_capped(env: Env) -> None:
    await env.add_user(16, child="Соня")
    limit = SKILL.meta.recent_memory
    for i in range(limit + 5):
        await env.service.record_sent(16, f"cm{i % 50 + 1:02d}", now=NOON + timedelta(minutes=i))
    recent = (await env.user(16)).cheer_recent
    assert recent is not None and len(recent) == limit
    message = await env.service.prepare(16, now=NOON)
    assert message.item_id not in recent or len(recent) >= 100


async def test_blocked_user_is_switched_off(env: Env) -> None:
    await env.add_user(16)
    session = ScriptedSession(fail_with=[forbidden()])
    assert await env.scheduler(session).run_once(NOON) == 0
    assert (await env.user(16)).cheer_freq == "off"


async def test_flood_control_is_retried_once(env: Env) -> None:
    await env.add_user(16)
    session = ScriptedSession(fail_with=[retry_after()])
    assert await env.scheduler(session).run_once(NOON) == 1
    assert len([c for c in session.calls if isinstance(c, SendMessage)]) == 1  # the retry


async def test_failed_send_does_not_record_history(env: Env) -> None:
    await env.add_user(16)
    session = ScriptedSession(fail_with=[retry_after(), retry_after()])
    assert await env.scheduler(session).run_once(NOON) == 0
    assert (await env.user(16)).cheer_recent is None
    assert (await env.user(16)).cheer_freq == "daily"  # temporary trouble, stays opted in


async def test_run_forever_survives_errors_and_stops_on_cancel(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def flaky(_: datetime | None = None) -> list[int]:
        nonlocal calls
        calls += 1
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(env.service, "claim_due", flaky)
    task = asyncio.create_task(env.scheduler(ScriptedSession()).run_forever())
    await asyncio.sleep(0.08)
    assert not task.done() and calls >= 2  # kept going after the error
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_settings_reject_an_empty_window() -> None:
    with pytest.raises(ValidationError):
        Settings(
            bot_token="1:T",
            llm_provider="fake",
            cheer_window_start=12,
            cheer_window_end=12,
            _env_file=None,
        )  # type: ignore[call-arg]


async def test_invitation_flag_flips_once(env: Env) -> None:
    await env.add_user(16, "off")
    async with env.sf.begin() as session:
        await repo.upsert_user(session, 99)
        assert await repo.mark_cheer_asked(session, 99) is True
        assert await repo.mark_cheer_asked(session, 99) is False


# --- Bot flows (real handlers, FakeLLM, SQLite) ---------------------------------------------------------------
async def db_user(app: App, client: Client) -> User:
    async with app.sf() as session:
        user = await session.get(User, client.user_id)
        assert user is not None
        return user


async def test_first_profile_triggers_a_single_invitation(app: App, client: Client) -> None:
    await onboard(client)
    assert client.calls.sent_texts().count(texts.CHEER_INVITE) == 1
    assert CheerCb(action="freq", value="weekly", src="invite").pack() in client.last_markup_data()
    assert (await db_user(app, client)).cheer_freq == "off"  # nothing is sent without a yes

    await client.send("/start")  # returning does not repeat the question
    await client.send("/menu")
    assert client.calls.sent_texts().count(texts.CHEER_INVITE) == 1


async def test_accepting_the_invitation_sets_the_frequency(app: App, client: Client) -> None:
    await onboard(client)
    await client.press(CheerCb(action="freq", value="weekly", src="invite"))
    assert (await db_user(app, client)).cheer_freq == "weekly"
    assert texts.cheer_freq_saved("weekly") in client.calls.edited_texts()


async def test_declining_the_invitation_keeps_it_off(app: App, client: Client) -> None:
    await onboard(client)
    await client.press(CheerCb(action="freq", value="off", src="invite"))
    user = await db_user(app, client)
    assert user.cheer_freq == "off" and user.cheer_asked is True
    assert texts.cheer_freq_saved("off") in client.calls.edited_texts()


async def test_cheer_on_request_by_mood(app: App, client: Client) -> None:
    await client.send("/cheer")
    assert texts.CHEER_ASK_MOOD in client.calls.sent_texts()
    offered = client.last_markup_data()
    for mood in (*MOODS, "any"):
        assert CheerCb(action="mood", mood=mood).pack() in offered

    await client.press(CheerCb(action="mood", mood="tired"))
    shown = client.calls.edited_texts()[-1]
    assert shown.split("\n\n")[0] in KB.frames.mood_openers["tired"]
    assert CheerCb(action="more", mood="tired").pack() in client.last_markup_data()
    recent = (await db_user(app, client)).cheer_recent
    assert recent and len(recent) == 1

    await client.press(CheerCb(action="more", mood="tired"))
    recent = (await db_user(app, client)).cheer_recent
    assert recent and len(recent) == 2 and recent[0] != recent[1]


async def test_main_menu_has_the_warm_words_button(client: Client) -> None:
    await onboard(client)
    await client.send("/menu")
    assert MenuCb(action="cheer").pack() in client.last_markup_data()
    await client.press(MenuCb(action="cheer"))
    assert texts.CHEER_ASK_MOOD in client.calls.edited_texts()


async def test_settings_show_and_change_the_frequency(app: App, client: Client) -> None:
    await client.press(MenuCb(action="settings"))
    assert any("Тёплые слова от Луны: <b>выкл</b>" in t for t in client.calls.edited_texts())
    assert CheerCb(action="freq_menu").pack() in client.last_markup_data()

    await client.press(CheerCb(action="freq_menu"))
    picker = client.last_markup_data()
    for freq in ("off", "weekly", "few", "daily"):
        assert CheerCb(action="freq", value=freq, src="settings").pack() in picker

    await client.press(CheerCb(action="freq", value="daily", src="settings"))
    assert (await db_user(app, client)).cheer_freq == "daily"
    assert any("<b>каждый день</b>" in t for t in client.calls.edited_texts())

    await client.press(MenuCb(action="settings"))
    assert any("Тёплые слова от Луны: <b>каждый день</b>" in t for t in client.calls.edited_texts())


async def test_mute_button_under_a_proactive_message(app: App, client: Client) -> None:
    await client.press(CheerCb(action="freq", value="daily", src="settings"))
    await client.press(CheerCb(action="freq", value="off", src="msg"))
    assert (await db_user(app, client)).cheer_freq == "off"
    assert texts.cheer_freq_saved("off") in client.calls.edited_texts()


async def test_bogus_frequency_is_ignored(app: App, client: Client) -> None:
    await client.press(CheerCb(action="freq", value="hourly", src="settings"))
    assert (await db_user(app, client)).cheer_freq == "off"


async def test_invite_once_helper_sends_only_the_first_time(app: App, client: Client) -> None:
    await client.send("/cheer")  # creates the user
    client.calls.calls.clear()
    await invite_once(app.bot, client.user_id, app.sf, client.user_id)
    await invite_once(app.bot, client.user_id, app.sf, client.user_id)
    assert client.calls.sent_texts() == [texts.CHEER_INVITE]


# --- Small talk -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Спасибо!", "thanks"),
        ("большое спасибо вам", "thanks"),
        ("Привет", "greeting"),
        ("Здравствуйте, Луна", "greeting"),
        ("Добрый вечер", "greeting"),
        ("я так устала сегодня", "tired"),
        ("Вымотался совсем", "tired"),
        ("мне тревожно", "anxious"),
        ("ничего не выходит", "stuck"),
        ("у меня не получается уложить его спать", "stuck"),
        ("его дома бьют", "crisis"),
        ("не хочу жить", "crisis"),
        ("расскажи про динозавров", None),
        ("абракадабра", None),
    ],
)
def test_smalltalk_classification(text: str, intent: str | None) -> None:
    assert smalltalk.classify(text) == intent


def test_smalltalk_replies_are_in_voice_and_offer_the_next_step() -> None:
    thanks = smalltalk.reply_to("спасибо", random.Random(1))
    assert thanks is not None and thanks.text in texts.SMALLTALK_THANKS
    tired = smalltalk.reply_to("устала", random.Random(1))
    assert tired is not None and tired.text == texts.SMALLTALK_MOOD["tired"]
    offered = [b.callback_data for row in tired.markup.inline_keyboard for b in row]
    assert CheerCb(action="mood", mood="tired").pack() in offered
    crisis = smalltalk.reply_to("не хочу жить")
    assert crisis is not None and crisis.text == texts.CRISIS_SUPPORT
    assert smalltalk.reply_to("абракадабра") is None


async def test_luna_answers_small_talk_in_chat(client: Client) -> None:
    await client.send("спасибо")
    assert any(t in client.calls.sent_texts() for t in texts.SMALLTALK_THANKS)

    await client.send("мне тревожно")
    assert texts.SMALLTALK_MOOD["anxious"] in client.calls.sent_texts()
    await client.press(CheerCb(action="mood", mood="anxious"))
    assert client.calls.edited_texts()[-1].split("\n\n")[0] in KB.frames.mood_openers["anxious"]

    await client.send("его дома бьют")
    assert texts.CRISIS_SUPPORT in client.calls.sent_texts()


async def test_unknown_text_still_gets_the_hint(client: Client) -> None:
    await client.send("абракадабра")
    assert texts.UNKNOWN in client.calls.sent_texts()
