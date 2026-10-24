from __future__ import annotations

import asyncio
import random

import pytest

from skazki_bot.db import repo
from skazki_bot.harness import GuardBlocked, InputRejected, TaleHarness
from skazki_bot.llm.base import LLMError
from skazki_bot.services.tale_service import (
    AlreadyGenerating,
    ChildNotFound,
    DailyLimitReached,
    TaleRequest,
    TaleService,
)
from tests.conftest import App
from tests.fakes import ScriptedChat, make_story, text_turn

GOOD = text_turn(make_story())


async def _make_child(app: App, user_id: int, *, age: int = 4) -> int:
    async with app.sf.begin() as s:
        await repo.upsert_user(s, user_id)
        child = await repo.create_child(
            s,
            user_id,
            name="Маша",
            gender="girl",
            age=age,
            interests=["animals"],
            extra_interests="",
        )
        return child.id


def _service(app: App, chat: ScriptedChat, **overrides: object) -> TaleService:
    settings = app.settings.model_copy(update={"critic_enabled": False, **overrides})
    harness = TaleHarness(llm=chat, registry=app.skills, settings=settings, rng=random.Random(1))
    return TaleService(sf=app.sf, harness=harness, settings=settings)


ORIGINAL = TaleRequest(skill="original")


async def _runs(app: App, user_id: int) -> list[str]:
    async with app.sf() as s:
        from sqlalchemy import select

        from skazki_bot.db.models import GenerationRun

        rows = await s.scalars(select(GenerationRun).where(GenerationRun.user_id == user_id))
        return [r.outcome for r in rows]


async def test_generate_saves_tale_and_run(app: App) -> None:
    child_id = await _make_child(app, 1)
    service = _service(app, ScriptedChat([GOOD]))
    seen: list[str] = []

    async def progress(text: str) -> None:
        seen.append(text)

    tale = await service.generate(
        user_id=1, child_id=child_id, request=ORIGINAL, on_progress=progress
    )
    assert tale.title == "Звёздный путь"
    assert tale.skill == "original"
    assert seen, "прогресс должен сообщаться"
    async with app.sf() as s:
        assert await repo.count_tales(s, 1, child_id) == 1
    assert await _runs(app, 1) == ["ok"]


async def test_too_short_answer_is_blocked_and_not_saved(app: App) -> None:
    child_id = await _make_child(app, 2)
    service = _service(app, ScriptedChat([text_turn("Название\n\nКоротко.")]))
    with pytest.raises(GuardBlocked):
        await service.generate(user_id=2, child_id=child_id, request=ORIGINAL)
    async with app.sf() as s:
        assert await repo.count_tales(s, 2, child_id) == 0
    assert await _runs(app, 2) == ["blocked"]


async def test_llm_failure_does_not_consume_quota(app: App) -> None:
    child_id = await _make_child(app, 3)
    service = _service(app, ScriptedChat([LLMError("boom")]))
    with pytest.raises(LLMError):
        await service.generate(user_id=3, child_id=child_id, request=ORIGINAL)
    assert await service.remaining_today(3) == app.settings.daily_tale_limit
    assert await _runs(app, 3) == ["error"]  # токены потрачены — след остаётся


async def test_daily_limit(app: App) -> None:
    child_id = await _make_child(app, 4)
    service = _service(app, ScriptedChat([GOOD]))
    for _ in range(app.settings.daily_tale_limit):
        await service.generate(user_id=4, child_id=child_id, request=ORIGINAL)
    assert await service.remaining_today(4) == 0
    with pytest.raises(DailyLimitReached):
        await service.generate(user_id=4, child_id=child_id, request=ORIGINAL)


async def test_admin_has_no_limit(app: App) -> None:
    service = _service(app, ScriptedChat([GOOD]), admin_ids=[5])
    assert await service.remaining_today(5) is None


async def test_unknown_child(app: App) -> None:
    service = _service(app, ScriptedChat([GOOD]))
    with pytest.raises(ChildNotFound):
        await service.generate(user_id=6, child_id=999_999, request=ORIGINAL)


async def test_cannot_use_someone_elses_child(app: App) -> None:
    child_id = await _make_child(app, 7)
    service = _service(app, ScriptedChat([GOOD]))
    with pytest.raises(ChildNotFound):
        await service.generate(user_id=8, child_id=child_id, request=ORIGINAL)


async def test_parallel_generation_is_rejected(app: App) -> None:
    child_id = await _make_child(app, 9)
    gate = asyncio.Event()
    service = _service(app, ScriptedChat([GOOD], gate=gate))
    first = asyncio.create_task(service.generate(user_id=9, child_id=child_id, request=ORIGINAL))
    await asyncio.sleep(0.05)
    with pytest.raises(AlreadyGenerating):
        await service.generate(user_id=9, child_id=child_id, request=ORIGINAL)
    gate.set()
    await first


async def test_timeout_is_an_llm_error_and_is_recorded(app: App) -> None:
    child_id = await _make_child(app, 10)
    service = _service(app, ScriptedChat([GOOD], gate=asyncio.Event()), harness_timeout_s=0.05)
    with pytest.raises(LLMError, match="время"):
        await service.generate(user_id=10, child_id=child_id, request=ORIGINAL)
    assert await _runs(app, 10) == ["error"]


async def test_rejected_input_creates_no_run(app: App) -> None:
    child_id = await _make_child(app, 11)
    chat = ScriptedChat([GOOD])
    service = _service(app, chat)
    with pytest.raises(InputRejected):
        await service.generate(
            user_id=11,
            child_id=child_id,
            request=TaleRequest(skill="original", idea="папа бьёт маму"),
        )
    assert chat.calls == []
    assert await _runs(app, 11) == []


async def test_classic_prompt_contains_story_and_seed_is_stored(app: App) -> None:
    child_id = await _make_child(app, 12)
    chat = ScriptedChat([GOOD])
    service = _service(app, chat)
    await service.generate(
        user_id=12, child_id=child_id, request=TaleRequest(skill="classic", classic_id="repka")
    )
    assert "Репка" in chat.calls[0]["messages"][0]["content"]
    async with app.sf() as s:
        stats = await repo.tale_stats(s, child_id)
    assert stats.seen["repka"] == 1


async def test_recent_tales_feed_the_memory(app: App) -> None:
    child_id = await _make_child(app, 13)
    service = _service(app, ScriptedChat([GOOD]))
    await service.generate(user_id=13, child_id=child_id, request=ORIGINAL)

    chat = ScriptedChat([GOOD])
    second = _service(app, chat)
    await second.generate(user_id=13, child_id=child_id, request=TaleRequest(skill=None))
    first_message = chat.calls[0]["messages"][0]["content"]
    assert "<recent_formats>" in first_message
    assert "original" in first_message


async def test_repo_delete_user_data_removes_everything(app: App) -> None:
    child_id = await _make_child(app, 14)
    service = _service(app, ScriptedChat([GOOD]))
    await service.generate(user_id=14, child_id=child_id, request=ORIGINAL)
    assert await _runs(app, 14) == ["ok"]

    async with app.sf.begin() as s:
        await repo.delete_user_data(s, 14)
    async with app.sf() as s:
        assert await repo.list_children(s, 14) == []
        assert await repo.count_tales(s, 14, child_id) == 0
    assert await _runs(app, 14) == []


async def test_repo_delete_active_child_promotes_another(app: App) -> None:
    first = await _make_child(app, 15)
    async with app.sf.begin() as s:
        second = await repo.create_child(
            s, 15, name="Ваня", gender="boy", age=6, interests=[], extra_interests=""
        )
        second_id = second.id
    async with app.sf.begin() as s:
        assert await repo.delete_child(s, 15, second_id)
    async with app.sf.begin() as s:
        active = await repo.get_active_child(s, 15)
    assert active is not None
    assert active.id == first
