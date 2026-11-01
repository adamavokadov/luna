"""World folk sources: schema, authoring rules, retrieval and prompt block (docs/FOLK_SOURCES.md)."""

from __future__ import annotations

import copy
import random
import re
import unicodedata
from typing import Any

import pytest
from pydantic import ValidationError

from skazki_bot.domain.age import profile_for_age
from skazki_bot.knowledge import find_folk_sources, folk_source_block, load_folk_sources
from skazki_bot.knowledge.__main__ import main as kb_check
from skazki_bot.knowledge.folk_sources import FolkSource, FolkSources, eligible_sources
from skazki_bot.stories.library import load_classics
from tests.test_knowledge import KNOWN_THEMES, cyrillic_share

# Dialogue lines and quotation marks are the sign of text pasted from a collection.
QUOTE_MARKS = re.compile(r"[«»“”„]")
DIALOGUE_DASH = re.compile(r"^\s*[-–—]")


def _emoji(text: str) -> bool:
    return any(unicodedata.category(ch) == "So" for ch in text)


def test_folk_sources_load_and_are_linked() -> None:
    folk = load_folk_sources()
    assert len(folk) >= 35
    assert len(folk.collections) >= 8
    classic_ids = {c.id for c in load_classics()}
    assert not classic_ids & {t.id for t in folk.tales}, "ids must not clash with classics.yaml"
    used = {t.collection for t in folk.tales}
    assert used == {c.id for c in folk.collections}, "every collection must have at least one plot"


def test_folk_sources_follow_authoring_rules() -> None:
    for tale in load_folk_sources().tales:
        assert set(tale.themes) <= KNOWN_THEMES, tale.id
        for text in tale.text_fields():
            assert cyrillic_share(text) >= 0.8, (tale.id, text[:40])
            assert not QUOTE_MARKS.search(text), (tale.id, text[:40])
            assert not DIALOGUE_DASH.search(text), (tale.id, text[:40])
            assert not _emoji(text), (tale.id, text[:40])
        assert len(set(tale.beats)) == len(tale.beats), tale.id
        if tale.scary >= 2:
            assert tale.ending_hint, tale.id


def test_every_age_and_bedtime_can_be_served() -> None:
    sources = load_folk_sources().tales
    for age in range(2, 11):
        daytime = eligible_sources(sources, age=age)
        night = eligible_sources(sources, age=age, bedtime=True)
        assert daytime, age
        assert night, age
        limit = profile_for_age(age).max_scary
        assert all(s.scary <= limit for s in daytime), age
        assert all(s.calm and s.scary <= 1 for s in night), age


def test_find_is_deterministic_age_safe_and_prefers_themes_and_unseen() -> None:
    sources = load_folk_sources().tales
    first = find_folk_sources(sources, age=6, themes=["dragons"], rng=random.Random(3))
    again = find_folk_sources(sources, age=6, themes=["dragons"], rng=random.Random(3))
    assert first == again
    assert len({s.id for s in first}) == len(first) == 3
    assert first[0].id == "chinese_belyy_drakon"
    assert all(s.min_age <= 6 <= s.max_age for s in first)

    seen = [first[0].id] * 3
    after = find_folk_sources(
        sources, age=6, themes=["dragons"], seen=seen, limit=1, rng=random.Random(3)
    )
    assert after[0].id != first[0].id

    night = find_folk_sources(sources, age=3, bedtime=True, limit=5, rng=random.Random(1))
    assert night
    assert all(s.calm and s.scary <= 1 for s in night)
    assert find_folk_sources(sources, age=5, limit=0) == []


def test_motifs_steer_the_pick() -> None:
    sources = load_folk_sources().tales
    picks = find_folk_sources(sources, age=8, motifs=["three_wishes"], limit=1)
    assert picks[0].id == "estonian_tri_zhelaniya"


def test_prompt_block_carries_plot_and_softening() -> None:
    folk = load_folk_sources()
    tale = next(t for t in folk.tales if t.id == "russian_ilya_solovey")
    block = folk_source_block(tale)
    assert block.startswith("Народный сюжет-основа")
    assert f"Название: {tale.title}" in block
    assert f"{len(tale.beats)}. {tale.beats[-1]}" in block
    assert f"Про финал: {tale.ending_hint}" in block
    plain = next(t for t in folk.tales if t.ending_hint is None)
    assert "Про финал" not in folk_source_block(plain)


def _raw() -> dict[str, Any]:
    tale = load_folk_sources().tales[0]
    return {
        "collections": [
            c.model_dump() for c in load_folk_sources().collections if c.id == tale.collection
        ],
        "tales": [tale.model_dump()],
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["tales"][0].update(beats=d["tales"][0]["beats"][:2]),  # too few beats
        lambda d: d["tales"][0].update(beats=["коротко", *d["tales"][0]["beats"][1:]]),
        lambda d: d["tales"][0].update(min_age=9, max_age=3),
        lambda d: d["tales"][0].update(scary=2, calm=False, ending_hint=None),
        lambda d: d["tales"][0].update(scary=3, calm=True),
        lambda d: d["tales"][0].update(motifs=["not_a_motif"]),
        lambda d: d["tales"][0].update(collection="nope"),
        lambda d: d["tales"].append(copy.deepcopy(d["tales"][0])),  # duplicate id
        lambda d: d["tales"][0].update(extra_field="x"),
    ],
)
def test_validation_rejects_broken_entries(mutate: Any) -> None:
    data = _raw()
    FolkSources.model_validate(data)  # the unmodified sample is valid
    mutate(data)
    with pytest.raises(ValidationError):
        FolkSources.model_validate(data)


def test_single_entry_model_is_frozen() -> None:
    tale: FolkSource = load_folk_sources().tales[0]
    with pytest.raises(ValidationError):
        tale.title = "other"  # type: ignore[misc]


def test_kb_check_reports_folk_sources(capsys: pytest.CaptureFixture[str]) -> None:
    assert kb_check() == 0
    assert "folk sources" in capsys.readouterr().out
