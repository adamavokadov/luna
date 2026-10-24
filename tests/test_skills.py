"""Навыки: встроенный набор валидируется как продукт, а загрузчик строго отвергает кривые навыки."""

from __future__ import annotations

from pathlib import Path

import pytest

from skazki_bot.bot.callbacks import TaleCb
from skazki_bot.harness.prompts import build_system
from skazki_bot.harness.skills import (
    BEDTIME,
    SkillError,
    SkillRegistry,
    builtin_skills_dir,
    load_skill_dir,
    scan_skills,
)
from skazki_bot.harness.skills_cli import main as skills_cli

EXPECTED = {
    "bedtime", "celebration", "classic", "cumulative", "educational", "funny", "life-event",
    "meditation", "metaphorical", "original", "rhyme", "riddles", "sequel", "values",
}  # fmt: skip


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    return SkillRegistry.load()


def test_builtin_set_is_complete(registry: SkillRegistry) -> None:
    assert {s.name for s in registry.all()} == EXPECTED


def test_every_builtin_skill_is_well_formed(registry: SkillRegistry) -> None:
    for skill in registry.all():
        assert skill.path.name == skill.name
        assert len(skill.body) > 400, skill.name  # методика, а не отписка
        if skill.meta.parent_note:
            assert "родител" in skill.body.lower(), (
                f"{skill.name}: нет описания раздела для родителей"
            )
        if skill.meta.input == "required":
            assert skill.presets or skill.meta.input_prompt
        for preset in skill.presets:
            packed = TaleCb(action="preset", skill=skill.name, idx=9, bedtime=True).pack()
            assert len(packed.encode()) <= 64, (skill.name, preset)
            assert len(preset) <= 40


def test_key_skills_have_expected_features(registry: SkillRegistry) -> None:
    bedtime = registry.get(BEDTIME)
    assert bedtime is not None
    assert bedtime.meta.overlay
    metaphorical = registry.get("metaphorical")
    assert metaphorical is not None
    assert metaphorical.meta.parent_note
    assert set(metaphorical.references) == {
        "references/metaphors.md",
        "references/sensitive-topics.md",
    }
    sequel = registry.get("sequel")
    assert sequel is not None
    assert sequel.allowed_tools == ("get_recent_tales",)
    assert [s.name for s in registry.overlays()] == [BEDTIME]


def test_catalog_and_system_prompt_stay_compact(registry: SkillRegistry) -> None:
    catalog = registry.catalog_text()
    for skill in registry.all():
        assert skill.name in catalog
    system = build_system(registry)
    assert "КАТАЛОГ НАВЫКОВ" in system
    assert len(system) < 14_000  # метаданные дёшевы — тела навыков не лежат в системном промпте
    assert all(s.body[:60] not in system for s in registry.all())


def test_eligibility_by_age_and_bedtime(registry: SkillRegistry) -> None:
    toddler = {s.name for s in registry.eligible(2)}
    assert {"original", "bedtime", "cumulative"} <= toddler
    assert not {"metaphorical", "riddles", "educational", "meditation"} & toddler

    calm = {s.name for s in registry.eligible(8, bedtime=True)}
    assert "meditation" in calm
    assert not {"funny", "riddles", "celebration", BEDTIME} & calm

    menu = {s.name for s in registry.eligible(8, menu_only=True)}
    assert "classic" not in menu
    assert "original" in menu


def test_read_reference_is_whitelisted(registry: SkillRegistry) -> None:
    text = registry.read_reference("metaphorical", "references/metaphors.md")
    assert text.startswith("# Каталог образов")
    for bad in ("../../etc/passwd", "references/../SKILL.md", "/etc/passwd", "references/none.md"):
        with pytest.raises(SkillError):
            registry.read_reference("metaphorical", bad)
    with pytest.raises(SkillError):
        registry.read_reference("no-such-skill", "references/metaphors.md")


# --- Валидация ----------------------------------------------------------------------------------
def write_skill(root: Path, name: str, front: str, body: str = "Тело навыка. " * 20) -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\n{front}\n---\n{body}\n", encoding="utf-8")
    return path


GOOD_FRONT = 'name: {name}\ndescription: "Хороший навык."\nmetadata:\n  title: "Заголовок"'


def test_minimal_skill_is_valid(tmp_path: Path) -> None:
    skill = load_skill_dir(write_skill(tmp_path, "mine", GOOD_FRONT.format(name="mine")))
    assert skill.title == "Заголовок"
    assert (skill.meta.min_age, skill.meta.max_age) == (2, 10)
    assert skill.references == ()


@pytest.mark.parametrize(
    ("name", "front", "message"),
    [
        (
            "mine",
            'name: other\ndescription: "x"\nmetadata:\n  title: "T"',
            "совпадать с именем папки",
        ),
        ("Bad_Name", 'name: Bad_Name\ndescription: "x"\nmetadata:\n  title: "T"', "строчные"),
        ("mine", 'name: mine\ndescription: "x"\ntitle: "T"', "вне спецификации"),
        ("mine", 'name: mine\ndescription: ""\nmetadata:\n  title: "T"', "пустой description"),
        (
            "mine",
            'name: mine\ndescription: "' + "а" * 301 + '"\nmetadata:\n  title: "T"',
            "длиннее",
        ),
        (
            "mine",
            'name: mine\ndescription: "x"\nmetadata:\n  title: "T"\n  min-age: "9"\n  max-age: "3"',
            "min-age",
        ),
        (
            "mine",
            'name: mine\ndescription: "x"\nmetadata:\n  title: "T"\n  input: "required"',
            "input-prompt",
        ),
        (
            "mine",
            'name: mine\ndescription: "x"\nmetadata:\n  title: "T"\nallowed-tools: rm_rf',
            "неизвестные инструменты",
        ),
        (
            "mine",
            'name: mine\ndescription: "x"\nmetadata:\n  title: "T"\n  surprise: "1"',
            "metadata",
        ),
        ("mine", 'name: mine\ndescription: "x"', "metadata"),
    ],
)
def test_invalid_skills_are_rejected(tmp_path: Path, name: str, front: str, message: str) -> None:
    path = write_skill(tmp_path, name, front)
    with pytest.raises(SkillError, match=message):
        load_skill_dir(path)


def test_missing_frontmatter_and_missing_file(tmp_path: Path) -> None:
    broken = tmp_path / "mine"
    broken.mkdir()
    with pytest.raises(SkillError, match="нет файла"):
        load_skill_dir(broken)
    (broken / "SKILL.md").write_text("Просто текст без frontmatter", encoding="utf-8")
    with pytest.raises(SkillError, match="frontmatter"):
        load_skill_dir(broken)


def test_body_limits_and_dangling_reference(tmp_path: Path) -> None:
    front = GOOD_FRONT.format(name="mine")
    too_long = write_skill(tmp_path / "a", "mine", front, "\n".join(["строка"] * 600))
    with pytest.raises(SkillError, match="500"):
        load_skill_dir(too_long)
    dangling = write_skill(
        tmp_path / "b", "mine", front, "См. references/ghost.md для деталей. " * 5
    )
    with pytest.raises(SkillError, match="ghost"):
        load_skill_dir(dangling)


def test_custom_dir_adds_and_overrides(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "bedtime",
        'name: bedtime\ndescription: "Своя версия."\nmetadata:\n  title: "Мой сон"\n  overlay: "true"',
        "Моё тело навыка. " * 30,
    )
    write_skill(tmp_path, "my-format", GOOD_FRONT.format(name="my-format"))
    registry = SkillRegistry.load(tmp_path)

    assert len(registry) == len(EXPECTED) + 1
    assert registry.get("bedtime") is not None
    assert registry.get("bedtime").title == "Мой сон"  # type: ignore[union-attr]
    assert registry.get("my-format") is not None
    assert "my-format" in build_system(registry)


def test_scan_missing_dir() -> None:
    with pytest.raises(SkillError):
        scan_skills(Path("/definitely/not/here"))


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert skills_cli([str(builtin_skills_dir())]) == 0
    assert "14 навыков" in capsys.readouterr().out
    write_skill(tmp_path, "mine", 'name: wrong\ndescription: "x"\nmetadata:\n  title: "T"')
    assert skills_cli([str(tmp_path)]) == 1
