"""Knowledge bases: schema, authoring rules, folk toolkit selection and its use in generation."""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Iterator

import pytest

from skazki_bot.cheer.compose import MOODS
from skazki_bot.config import Settings
from skazki_bot.domain.enums import Gender
from skazki_bot.domain.interests import INTERESTS
from skazki_bot.harness import ChildSnapshot, RunInput, RunRequest, SkillRegistry, TaleHarness
from skazki_bot.harness.prompts import build_system
from skazki_bot.knowledge import load_cheer_kb, load_folk_toolkit, pick_toolkit
from skazki_bot.knowledge.__main__ import main as kb_check
from skazki_bot.knowledge.cheer_kb import CheerKB
from skazki_bot.knowledge.tale_kb import FolkToolkit, toolkit_prompt
from skazki_bot.stories.library import load_classics
from tests.fakes import ScriptedChat, make_story, text_turn

# --- Authoring rules for warm words (see docs/KNOWLEDGE.md) -----------------------------------------
ROLE_WORDS = re.compile(r"\b(?:мам\w*|пап\w*|мать|матер\w*|отец|отц\w*)\b", re.IGNORECASE)
# «вы очень заботливая»: a gendered predicate about the reader (the sex of the reader is unknown)
GENDERED_AFTER_YOU = re.compile(
    r"\bвы\s+(?:(?:очень|так|действительно|по-настоящему|ещё|уже|всё)\s+)?\w+(?:ая|яя|ый|ий|ой)\b",
    re.IGNORECASE,
)
GENDER_SUFFIX = re.compile(r"\((?:а|ла|ый|ая)\)")
PREPOSITION_BEFORE_NAME = re.compile(
    r"\b(?:для|у|с|со|к|о|об|про|без|от|из|за|на|в|до|при|над|под|перед)\s+\{child\}",
    re.IGNORECASE,
)
MASCULINE_LUNA = re.compile(r"\b(?:заглянул|хотел|подобрал|рад|готов)\b", re.IGNORECASE)


def cyrillic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum("\u0400" <= c <= "\u04ff" for c in letters) / len(letters) if letters else 1.0


def symbols(text: str) -> int:
    """Emoji-like characters (Unicode category So)."""
    return sum(unicodedata.category(c) == "So" for c in text)


def reader_texts(kb: CheerKB) -> Iterator[tuple[str, str]]:
    for kind in ("compliment", "encouragement", "proverb"):
        for item in kb.items(kind):  # type: ignore[arg-type]
            yield item.id, item.text
            if item.note:
                yield f"{item.id}/note", item.note


def frame_lines(kb: CheerKB) -> Iterator[str]:
    frames = kb.frames
    for group in (frames.openers, frames.mood_openers, frames.closers):
        for lines in group.values():
            yield from lines


def violations(text: str) -> list[str]:
    found = []
    if ROLE_WORDS.search(text):
        found.append("role word")
    if GENDERED_AFTER_YOU.search(text):
        found.append("gendered predicate after «вы»")
    if GENDER_SUFFIX.search(text):
        found.append("(а)-style suffix")
    if PREPOSITION_BEFORE_NAME.search(text):
        found.append("{child} outside the nominative case")
    return found


def test_the_checker_itself_catches_what_it_should() -> None:
    assert violations("Вы очень заботливая мама.") == ["role word", "gendered predicate after «вы»"]
    assert violations("Вы устал(а), а ребёнок спит.") == ["(а)-style suffix"]
    assert violations("Для {child} вы — всё.") == ["{child} outside the nominative case"]
    assert violations("Вы молодец, вы справляетесь, вы вправе передохнуть.") == []
    assert violations("Для ребёнка вы — самый нужный человек.") == []


# --- Warm words -------------------------------------------------------------------------------------
def test_cheer_kb_is_valid_and_rich_enough() -> None:
    kb = load_cheer_kb()
    assert len(kb) >= 100
    for mood in MOODS:
        count = sum(
            mood in i.moods
            for kind in ("compliment", "encouragement", "proverb")
            for i in kb.items(kind)
        )  # type: ignore[arg-type]
        assert count >= 6, f"too little material for mood {mood!r}: {count}"
    for part in ("morning", "day", "evening"):
        for kind in ("compliment", "encouragement"):
            usable = [
                i
                for i in kb.items(kind)  # type: ignore[arg-type]
                if "any" in i.moods and ("any" in i.times or part in i.times) and not i.child
            ]
            assert len(usable) >= 8, f"{kind} for {part}: {len(usable)}"


def test_cheer_texts_follow_authoring_rules() -> None:
    kb = load_cheer_kb()
    problems = {key: found for key, text in reader_texts(kb) if (found := violations(text))}
    assert not problems, problems
    for key, text in reader_texts(kb):
        assert cyrillic_share(text) >= 0.85, key
        assert symbols(text) == 0, f"{key}: emoji belong to frames, not to items"
        assert text.strip() == text and "  " not in text, key


def test_cheer_texts_are_unique_and_proverbs_are_proper() -> None:
    kb = load_cheer_kb()
    texts = [t for key, t in reader_texts(kb) if "/" not in key]
    assert len(texts) == len(set(texts))
    for proverb in kb.proverbs:
        assert proverb.text.endswith(".") and proverb.note, proverb.id
        assert proverb.note.endswith("."), proverb.id


def test_frames_speak_in_luna_voice() -> None:
    kb = load_cheer_kb()
    for line in frame_lines(kb):
        assert cyrillic_share(line) >= 0.8, line
        assert symbols(line) <= 1, f"at most one emoji per frame line: {line}"
        assert not MASCULINE_LUNA.search(line), line
        assert not ROLE_WORDS.search(line), line
        assert not GENDERED_AFTER_YOU.search(line), line


def test_child_items_use_the_name_only_as_a_subject() -> None:
    kb = load_cheer_kb()
    with_name = [i for k in ("compliment", "encouragement") for i in kb.items(k) if i.child]  # type: ignore[arg-type]
    assert len(with_name) >= 5
    for item in with_name:
        assert item.text.count("{child}") == 1
        assert not PREPOSITION_BEFORE_NAME.search(item.text), item.id


def test_kb_schema_rejects_bad_items() -> None:
    from pydantic import ValidationError

    from skazki_bot.knowledge.cheer_kb import CheerItem

    with pytest.raises(ValidationError):  # {child} used but not declared
        CheerItem(id="cm99", text="{child} растёт рядом с вами и учится.")
    with pytest.raises(ValidationError):  # unknown placeholder
        CheerItem(id="cm99", text="Вы справляетесь, {name}, и это видно.")
    with pytest.raises(ValidationError):  # wrong id prefix
        CheerItem(id="xx01", text="Вы справляетесь, и это видно.")
    with pytest.raises(ValidationError):  # unknown mood
        CheerItem.model_validate(
            {"id": "cm99", "text": "Вы справляетесь, и это видно.", "moods": ["sad"]}
        )


# --- Tale knowledge base ----------------------------------------------------------------------------
KNOWN_THEMES = {
    # classic plots
    "animals", "forest", "farm", "adventure", "magic", "fairies", "kingdom", "sea", "winter",
    "home", "food", "friendship", "nature", "insects", "music",
    # extra themes from the interest catalog
    "dinosaurs", "space", "transport", "technology", "dragons", "sport", "art",
}  # fmt: skip


def test_classic_plots_cover_more_ground_and_use_known_themes() -> None:
    classics = load_classics()
    assert len(classics) >= 25
    ids = {c.id for c in classics}
    assert {"petushok", "snegurochka", "kot_v_sapogah", "zolushka", "sivka_burka"} <= ids
    for classic in classics:
        assert set(classic.themes) <= KNOWN_THEMES, classic.id
    interest_themes = {t for i in INTERESTS for t in i.themes}
    assert interest_themes <= KNOWN_THEMES


def test_folk_toolkit_is_valid() -> None:
    toolkit = load_folk_toolkit()
    assert len(toolkit) >= 50
    for group in toolkit.groups():
        for entry in group:
            assert cyrillic_share(entry.text) >= 0.8, entry.id
            assert set(entry.themes) <= KNOWN_THEMES, entry.id


@pytest.mark.parametrize("bedtime", [False, True])
def test_toolkit_pick_fits_every_age(bedtime: bool) -> None:
    toolkit = load_folk_toolkit()
    for age in range(2, 11):
        for seed in range(20):
            pick = pick_toolkit(
                toolkit, age=age, bedtime=bedtime, themes={"animals"}, rng=random.Random(seed)
            )
            for entry in (pick.opening, pick.helper, pick.magic_object):
                assert entry.min_age <= age <= entry.max_age, (age, entry.id)
                assert entry.calm or not bedtime, entry.id
            assert pick.closing.min_age <= age <= pick.closing.max_age
            assert pick.closing.calm or not bedtime
            assert (pick.refrain is not None) == (age <= 7)


def test_toolkit_pick_is_deterministic_and_prefers_matching_themes() -> None:
    toolkit = load_folk_toolkit()
    first = pick_toolkit(toolkit, age=5, bedtime=False, themes=set(), rng=random.Random(1))
    again = pick_toolkit(toolkit, age=5, bedtime=False, themes=set(), rng=random.Random(1))
    assert first == again

    sea = sum(
        "sea"
        in pick_toolkit(
            toolkit, age=5, bedtime=False, themes={"sea"}, rng=random.Random(s)
        ).opening.themes
        for s in range(200)
    )
    neutral = sum(
        "sea"
        in pick_toolkit(
            toolkit, age=5, bedtime=False, themes=set(), rng=random.Random(s)
        ).opening.themes
        for s in range(200)
    )
    assert sea > neutral


def test_toolkit_prompt_lists_the_picked_blocks() -> None:
    toolkit = load_folk_toolkit()
    pick = pick_toolkit(toolkit, age=4, bedtime=True, themes=set(), rng=random.Random(2))
    prompt = toolkit_prompt(pick)
    assert pick.opening.text in prompt and pick.closing.text in prompt
    assert pick.helper.text in prompt and pick.magic_object.text in prompt
    assert pick.refrain is not None and pick.refrain.text in prompt
    old = pick_toolkit(toolkit, age=9, bedtime=False, themes=set(), rng=random.Random(2))
    assert "Припев" not in toolkit_prompt(old)


def test_toolkit_schema_rejects_duplicates() -> None:
    from pydantic import ValidationError

    toolkit = load_folk_toolkit().model_dump()
    toolkit["closings"][0]["id"] = toolkit["openings"][0]["id"]
    with pytest.raises(ValidationError):
        FolkToolkit.model_validate(toolkit)


# --- The toolkit and the persona in generation ---------------------------------------------------------
@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    return SkillRegistry.load()


def harness_for(registry: SkillRegistry, chat: ScriptedChat) -> TaleHarness:
    settings = Settings(bot_token="1:T", llm_provider="fake", critic_enabled=False, _env_file=None)  # type: ignore[call-arg]
    return TaleHarness(
        llm=chat,
        registry=registry,
        settings=settings,
        rng=random.Random(3),
        toolkit_rng=random.Random(5),
    )


def child_input(
    *, skill: str | None = "original", idea: str | None = None, bedtime: bool = False
) -> RunInput:
    return RunInput(
        child=ChildSnapshot("Маша", Gender.GIRL, 4, ("animals",), ""),
        request=RunRequest(skill=skill, bedtime=bedtime, idea=idea),
    )


def first_user_message(chat: ScriptedChat) -> str:
    content = chat.calls[0]["messages"][0]["content"]
    assert isinstance(content, str)
    return content


async def test_tale_request_carries_folk_toolkit_without_extra_tools(
    registry: SkillRegistry,
) -> None:
    chat = ScriptedChat([text_turn(make_story())])
    await harness_for(registry, chat).run(child_input())

    message = first_user_message(chat)
    assert "<folk_toolkit>" in message and "Зачин:" in message and "Концовка:" in message
    assert chat.calls[0]["tools"] == []  # the toolkit is data, not a tool: still a single turn
    assert message.index("<folk_toolkit>") < message.index("<task>")


async def test_heavy_topics_get_no_playful_formulas(registry: SkillRegistry) -> None:
    chat = ScriptedChat([text_turn(make_story())])
    await harness_for(registry, chat).run(child_input(idea="Бабушка заболела, мы скучаем"))
    assert "<folk_toolkit>" not in first_user_message(chat)
    assert "<safety_note>" in first_user_message(chat)


async def test_bedtime_toolkit_is_calm(registry: SkillRegistry) -> None:
    chat = ScriptedChat([text_turn(make_story())])
    await harness_for(registry, chat).run(child_input(bedtime=True))
    message = first_user_message(chat)
    toolkit = load_folk_toolkit()
    calm_closings = {e.text for e in (*toolkit.closings, *toolkit.lullabies) if e.calm}
    closing = next(line for line in message.splitlines() if line.startswith("Концовка: "))
    assert closing.removeprefix("Концовка: ") in calm_closings


def test_system_prompt_is_written_by_luna(registry: SkillRegistry) -> None:
    from skazki_bot.persona import load_persona

    system = build_system(registry)
    assert system.startswith(load_persona().prompt)
    assert "сказочник:" not in system  # the anonymous narrator is gone


def test_kb_check_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert kb_check() == 0
    out = capsys.readouterr().out
    assert (
        "classic plots" in out
        and "warm words" in out
        and "persona" in out
        and "skill: cheer" in out
    )
