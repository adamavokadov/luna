"""World folk plots in the harness: when the bot offers one, which one, and how it is recorded."""

from __future__ import annotations

import random
import re
from collections import Counter
from typing import Any

import pytest

from skazki_bot.config import Settings
from skazki_bot.domain.age import profile_for_age
from skazki_bot.domain.enums import Gender
from skazki_bot.harness import (
    ChildSnapshot,
    RunInput,
    RunRequest,
    SkillRegistry,
    TaleHarness,
)
from skazki_bot.knowledge import (
    hints_for_idea,
    load_folk_sources,
    load_idea_hints,
    pick_folk_source,
)
from skazki_bot.knowledge.folk_sources import FolkSource
from tests.fakes import ScriptedChat, make_story, text_turn, tool_turn
from tests.test_knowledge import KNOWN_THEMES


class Greedy(random.Random):
    """Always takes the heaviest candidate: removes the weighted randomness from a test."""

    def choices(  # type: ignore[override]
        self, population: Any, weights: Any = None, *, cum_weights: Any = None, k: int = 1
    ) -> list[Any]:
        best = max(range(len(population)), key=weights.__getitem__)
        return [population[best]]


PLOTS = {t.id: t for t in load_folk_sources().tales}
BY_TITLE = {t.title: t for t in PLOTS.values()}


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    return SkillRegistry.load()


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"bot_token": "1:T", "llm_provider": "fake", "critic_enabled": False}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def harness_for(registry: SkillRegistry, chat: ScriptedChat, **overrides: Any) -> TaleHarness:
    return TaleHarness(
        llm=chat,
        registry=registry,
        settings=make_settings(**overrides),
        rng=random.Random(3),
        folk_rng=random.Random(5),
    )


def run_input(
    *,
    skill: str | None = None,
    bedtime: bool = False,
    idea: str | None = None,
    age: int = 6,
    extra: str = "",
    seen: Counter[str] | None = None,
) -> RunInput:
    child = ChildSnapshot("Маша", Gender.GIRL, age, ("animals",), extra)
    return RunInput(
        child=child,
        request=RunRequest(skill=skill, bedtime=bedtime, idea=idea),
        seen=seen or Counter(),
    )


def first_message(chat: ScriptedChat) -> str:
    content = chat.calls[0]["messages"][0]["content"]
    assert isinstance(content, str)
    return content


def plot_in(message: str) -> FolkSource:
    match = re.search(r"<folk_source>\n.*?Название: (.+?)\n", message, flags=re.DOTALL)
    assert match, "no <folk_source> block in the message"
    return BY_TITLE[match.group(1)]


async def explicit(registry: SkillRegistry, skill: str, **kw: Any) -> tuple[str, Any]:
    chat = ScriptedChat([text_turn(make_story())])
    result = await harness_for(registry, chat).run(run_input(skill=skill, **kw))
    return first_message(chat), result


# --- Какие форматы получают сюжет ---------------------------------------------------------------
async def test_plot_based_format_gets_a_folk_plot_and_it_is_recorded(
    registry: SkillRegistry,
) -> None:
    message, result = await explicit(registry, "original")
    plot = plot_in(message)
    assert "взяв за основу народный сюжет из <folk_source>" in message
    assert plot.summary in message
    assert all(f"{i}. {b}" in message for i, b in enumerate(plot.beats, start=1))
    assert result.seed_id == plot.id
    assert result.mode == "folk"


@pytest.mark.parametrize("skill", ["rhyme", "values", "bedtime"])
async def test_other_plot_formats_opt_in(registry: SkillRegistry, skill: str) -> None:
    message, result = await explicit(registry, skill)
    assert "<folk_source>" in message
    assert result.mode == "folk"


@pytest.mark.parametrize(
    "skill", ["cumulative", "funny", "riddles", "celebration", "sequel", "educational"]
)
async def test_formats_with_their_own_structure_get_no_plot(
    registry: SkillRegistry, skill: str
) -> None:
    message, result = await explicit(registry, skill)
    assert "<folk_source>" not in message
    assert result.seed_id is None
    assert result.mode == "original"


async def test_classic_format_keeps_its_own_plot(registry: SkillRegistry) -> None:
    message, result = await explicit(registry, "classic")
    assert "<classic_story>" in message
    assert "<folk_source>" not in message
    assert result.mode == "classic"


async def test_skills_that_opt_in_are_exactly_these(registry: SkillRegistry) -> None:
    modes = {s.name: s.meta.folk_source for s in registry.all() if s.meta.folk_source != "none"}
    assert modes == {"original": "open", "rhyme": "open", "bedtime": "open", "values": "motif"}


# --- Идея родителя важнее -----------------------------------------------------------------------
async def test_parents_idea_wins_over_a_folk_plot(registry: SkillRegistry) -> None:
    message, result = await explicit(
        registry, "original", idea="про дракончика, который боится огня"
    )
    assert "<folk_source>" not in message
    assert "<idea>" in message
    assert result.seed_id is None


async def test_value_idea_steers_the_plot_by_motif(registry: SkillRegistry) -> None:
    message, result = await explicit(registry, "values", idea="Говорить правду")
    plot = plot_in(message)
    assert "honesty" in plot.motifs
    assert "Сюжет должен служить мысли из <idea>." in message
    assert result.seed_id == plot.id

    unknown, plain = await explicit(registry, "values", idea="про трактор и снегопад")
    assert "<folk_source>" not in unknown
    assert plain.seed_id is None


async def test_sensitive_topic_and_kill_switch_turn_it_off(registry: SkillRegistry) -> None:
    chat = ScriptedChat([text_turn(make_story())])
    await harness_for(registry, chat).run(run_input(skill="original", extra="умерла бабушка"))
    assert "<folk_source>" not in first_message(chat)
    assert "<safety_note>" in first_message(chat)

    off = ScriptedChat([text_turn(make_story())])
    result = await harness_for(registry, off, folk_sources_enabled=False).run(
        run_input(skill="original")
    )
    assert "<folk_source>" not in first_message(off)
    assert result.seed_id is None


# --- «Удиви меня» -------------------------------------------------------------------------------
async def test_surprise_me_offers_a_plot_and_records_it_if_the_format_can_use_it(
    registry: SkillRegistry,
) -> None:
    chat = ScriptedChat([tool_turn("load_skill", {"name": "original"}), text_turn(make_story())])
    result = await harness_for(registry, chat).run(run_input())
    message = first_message(chat)
    assert "не вызывай pick_classic" in message
    assert result.seed_id == plot_in(message).id
    assert result.mode == "folk"


async def test_surprise_me_does_not_record_a_plot_for_a_format_that_ignores_it(
    registry: SkillRegistry,
) -> None:
    chat = ScriptedChat([tool_turn("load_skill", {"name": "riddles"}), text_turn(make_story())])
    result = await harness_for(registry, chat).run(run_input())
    assert "<folk_source>" in first_message(chat)
    assert result.skill == "riddles"
    assert result.seed_id is None
    assert result.mode == "original"


async def test_surprise_me_with_an_idea_has_no_plot(registry: SkillRegistry) -> None:
    chat = ScriptedChat([tool_turn("load_skill", {"name": "original"}), text_turn(make_story())])
    result = await harness_for(registry, chat).run(run_input(idea="про робота-друга"))
    assert "<folk_source>" not in first_message(chat)
    assert result.seed_id is None


# --- Подбор «правильного» сюжета ----------------------------------------------------------------
@pytest.mark.parametrize("age", range(2, 11))
async def test_the_plot_always_fits_the_age_and_bedtime(registry: SkillRegistry, age: int) -> None:
    for bedtime in (False, True):
        message, _ = await explicit(registry, "original", age=age, bedtime=bedtime)
        plot = plot_in(message)
        limit = (
            min(profile_for_age(age).max_scary, 1) if bedtime else profile_for_age(age).max_scary
        )
        assert plot.scary <= limit, (age, bedtime, plot.id)
        if bedtime:
            assert plot.calm, (age, plot.id)


async def test_history_steers_away_from_seen_plots(registry: SkillRegistry) -> None:
    eligible = [t for t in PLOTS.values() if t.min_age <= 6 <= t.max_age and t.scary <= 2]
    unseen = eligible[0]
    seen = Counter({t.id: 2 for t in eligible[1:]})
    chat = ScriptedChat([text_turn(make_story())])
    harness = TaleHarness(llm=chat, registry=registry, settings=make_settings(), folk_rng=Greedy(1))
    await harness.run(run_input(skill="original", seen=seen))
    assert plot_in(first_message(chat)).id == unseen.id


async def test_folk_selection_does_not_shift_classic_selection(registry: SkillRegistry) -> None:
    async def classic_id(folk_seed: int) -> str | None:
        chat = ScriptedChat([text_turn(make_story())])
        harness = TaleHarness(
            llm=chat,
            registry=registry,
            settings=make_settings(),
            rng=random.Random(9),
            folk_rng=random.Random(folk_seed),
        )
        return (await harness.run(run_input(skill="classic"))).seed_id

    assert await classic_id(1) == await classic_id(2)


# --- pick_folk_source и подсказки по идее -------------------------------------------------------
def test_pick_prefers_good_scores_avoids_disliked_and_handles_empty() -> None:
    sources = load_folk_sources().tales
    liked = next(t for t in sources if t.min_age <= 6 <= t.max_age and t.scary <= 2)
    picks = {
        pick_folk_source(sources, age=6, liked=[liked.id], rng=random.Random(i)).id  # type: ignore[union-attr]
        for i in range(40)
    }
    assert liked.id in picks
    bad = {
        pick_folk_source(sources, age=6, disliked=[liked.id], rng=random.Random(i)).id  # type: ignore[union-attr]
        for i in range(40)
    }
    assert liked.id not in bad
    assert pick_folk_source([], age=6) is None


def test_idea_hints_are_valid_and_map_real_ideas() -> None:
    hints = load_idea_hints()
    assert len(hints) >= 10
    assert all(set(h.themes) <= KNOWN_THEMES for h in hints)
    # every motif a hint can ask for exists in at least one plot
    available = {m for t in load_folk_sources().tales for m in t.motifs}
    assert {m for h in hints for m in h.motifs} <= available

    assert hints_for_idea("Говорить правду")[0] == ["honesty"]
    motifs, _ = hints_for_idea("Делиться")
    assert "community" in motifs
    assert hints_for_idea("про трактор и снегопад") == ([], [])
    assert hints_for_idea("Быть смелым")[0][:1] == ["courage"]
