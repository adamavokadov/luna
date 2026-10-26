"""The patch tooling itself (tools/patchkit): build a patch from two small trees, check the contract."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "tools" / "patchkit"
APP_OLD = "".join(f"line {i}\n" for i in range(1, 41))
APP_NEW = APP_OLD.replace("line 5\n", "line 5 changed\n").replace(
    "line 35\n", "line 35 changed\nextra\n"
)
TRICKY = (
    "# a comment line\n#@@@BLOCK fake\n\n   leading spaces and trailing  \nПривет, мир ✨\n"
    "#\n# #\nno newline at the end"
)
HANDOFF = "# HANDOFF\n\n<!-- HANDOFF:LOG:BEGIN -->\n<!-- HANDOFF:LOG:END -->\n"
CONFIG = """
PATCH_ID = "0099-test"
TITLE = "test patch"
COMMIT_MESSAGE = "test: subject\\n\\nbody"
DOC = "test patch"
MOVES = {"new/data.yaml": "old/data.yaml"}
OVERWRITE = {"README.md"}
APPEND_LINES = {".gitignore"}
IF_MISSING = {".editorconfig"}
"""
ENTRY = "### 2026-10-24 — patch 0099-test\n\nDid things.\n"


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes().decode("utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".patch-backups" not in p.parts
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("patchkit")
    pristine, work = base / "pristine", base / "work"
    common = {
        "pyproject.toml": '[project]\nname = "skazki-bot"\n',
        "HANDOFF.md": HANDOFF,
        "src/app.py": APP_OLD,
        "old/data.yaml": "a: 1\n",
        ".gitignore": "__pycache__/\n.env\n",
        "README.md": "old readme\n",
    }
    write_tree(pristine, common)
    changed = {k: v for k, v in common.items() if k != "old/data.yaml"}
    changed.update(
        {
            "src/app.py": APP_NEW,
            "new/data.yaml": "a: 1\nb: 2\n",
            "new/tricky.txt": TRICKY,
            ".gitignore": "__pycache__/\n.env\n.venv/\n/patch_*.py\n",
            "README.md": "new readme\n",
            ".editorconfig": "root = true\n",
        }
    )
    write_tree(work, changed)
    config, entry, script = base / "config.py", base / "entry.md", base / "patch_0099_test.py"
    config.write_text(CONFIG, encoding="utf-8")
    entry.write_text(ENTRY, encoding="utf-8")
    subprocess.run(
        [sys.executable, str(KIT / "build_patch.py"), str(pristine), str(work), str(script),
         "--config", str(config), "--handoff", str(entry)],
        check=True, capture_output=True,
    )  # fmt: skip
    return {"pristine": pristine, "work": work, "script": script}


@pytest.fixture
def target(built: dict[str, Path], tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(built["pristine"], root)
    return root


def run(built: dict[str, Path], root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(built["script"]), "--root", str(root), *flags],
        capture_output=True, text=True,
    )  # fmt: skip


def expected(built: dict[str, Path]) -> dict[str, str]:
    files = snapshot(built["work"])
    # .gitignore is merged: missing entries are appended under a marker, never replaced
    files[".gitignore"] = (
        "__pycache__/\n.env\n\n# --- added by patch 0099-test ---\n.venv/\n/patch_*.py\n"
    )
    files["HANDOFF.md"] = HANDOFF.replace(
        "<!-- HANDOFF:LOG:BEGIN -->", "<!-- HANDOFF:LOG:BEGIN -->\n\n" + ENTRY.strip() + "\n"
    )
    return files


def test_dry_run_writes_nothing(built: dict[str, Path], target: Path) -> None:
    before = snapshot(target)
    result = run(built, target, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Dry run" in result.stdout and "new/tricky.txt" in result.stdout
    assert snapshot(target) == before
    assert not (target / ".patch-backups").exists()


def test_apply_produces_exactly_the_worked_tree(built: dict[str, Path], target: Path) -> None:
    result = run(built, target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(target) == expected(built)  # includes byte-exact tricky content
    assert not (target / "old").exists()  # the move leaves no empty directory behind
    assert (target / ".patch-backups" / "0099-test").is_dir()
    assert "git commit" in result.stdout
    assert "patch scripts" not in result.stdout  # nothing left over, nothing to say


def test_second_run_is_a_no_op(built: dict[str, Path], target: Path) -> None:
    run(built, target)
    after_first = snapshot(target)
    result = run(built, target)
    assert result.returncode == 0 and "Already applied" in result.stdout
    assert snapshot(target) == after_first


def test_anchor_drift_fails_without_partial_writes(built: dict[str, Path], target: Path) -> None:
    (target / "src/app.py").write_text(APP_OLD.replace("line 5\n", "line five\n"), encoding="utf-8")
    before = snapshot(target)
    result = run(built, target)
    assert result.returncode == 1
    assert "anchor not found" in result.stdout and "Nothing was changed" in result.stdout
    assert snapshot(target) == before  # not even the new files


def test_existing_files_are_respected(built: dict[str, Path], target: Path) -> None:
    write_tree(target, {".editorconfig": "mine = true\n", "new/tricky.txt": "my version\n"})
    result = run(built, target)
    assert result.returncode == 0, result.stdout
    assert (target / ".editorconfig").read_text(encoding="utf-8") == "mine = true\n"
    assert (target / "new/tricky.txt").read_text(encoding="utf-8") == "my version\n"
    assert "left untouched" in result.stdout


def test_gitignore_is_merged_not_replaced(built: dict[str, Path], target: Path) -> None:
    (target / ".gitignore").write_text("mine/\n.env\n", encoding="utf-8")
    assert run(built, target).returncode == 0
    lines = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "mine/" in lines and ".venv/" in lines and "/patch_*.py" in lines
    assert lines.count(".env") == 1


def test_rollback_restores_the_original_tree(built: dict[str, Path], target: Path) -> None:
    before = snapshot(target)
    run(built, target)
    result = run(built, target, "--rollback")
    assert result.returncode == 0, result.stdout
    assert snapshot(target) == before
    again = run(built, target, "--rollback")
    assert again.returncode == 1 and "nothing to roll back" in again.stdout


def test_refuses_to_run_in_the_wrong_directory(built: dict[str, Path], tmp_path: Path) -> None:
    result = run(built, tmp_path)
    assert result.returncode == 1 and "does not look like" in result.stdout


def test_builder_refuses_deletions(built: dict[str, Path], tmp_path: Path) -> None:
    work = tmp_path / "work"
    shutil.copytree(built["pristine"], work)
    (work / "README.md").unlink()
    config, entry = tmp_path / "config.py", tmp_path / "entry.md"
    config.write_text(
        CONFIG.replace('MOVES = {"new/data.yaml": "old/data.yaml"}', "MOVES = {}"), encoding="utf-8"
    )
    entry.write_text(ENTRY, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(KIT / "build_patch.py"), str(built["pristine"]), str(work),
         str(tmp_path / "out.py"), "--config", str(config), "--handoff", str(entry)],
        capture_output=True, text=True,
    )  # fmt: skip
    assert result.returncode != 0 and "unexpected deletions" in result.stderr


def test_verify_explains_a_missing_uv_instead_of_crashing(
    built: dict[str, Path], target: Path, tmp_path: Path
) -> None:
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    result = subprocess.run(
        [sys.executable, str(built["script"]), "--root", str(target), "--verify"],
        capture_output=True, text=True, env={"PATH": str(empty_path)},
    )  # fmt: skip
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert "uv and make not found" in result.stdout and "pip install uv" in result.stdout
    assert snapshot(target) == expected(built)  # the patch itself was applied


def test_next_steps_mention_installing_uv_when_it_is_missing(
    built: dict[str, Path], target: Path, tmp_path: Path
) -> None:
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    result = subprocess.run(
        [sys.executable, str(built["script"]), "--root", str(target)],
        capture_output=True, text=True, env={"PATH": str(empty_path)},
    )  # fmt: skip
    assert result.returncode == 0
    assert "pip install uv" in result.stdout


def test_next_steps_list_only_finished_patch_scripts_and_never_delete_them(
    built: dict[str, Path], target: Path
) -> None:
    scripts = {
        "patch_0001_old_one.py": "manifest.json",  # applied: listed
        "patch_0002_old_two.py": "manifest.json",  # applied: listed
        "patch_0003_pending.py": None,  # never applied (a later patch of a chain): must survive the hint
        "patch_0004_undone.py": "manifest.rolled-back.json",  # applied, then rolled back: not finished
    }
    for name, manifest in scripts.items():
        write_tree(target, {name: "# stand-in\n"})
        if manifest:
            run = (
                target
                / ".patch-backups"
                / name.removeprefix("patch_").removesuffix(".py").replace("_", "-")
            )
            write_tree(run / "20260101-000000", {manifest: "{}\n"})
    me = target / built["script"].name
    shutil.copy(built["script"], me)  # the running script must not list itself
    result = subprocess.run(
        [sys.executable, str(me), "--root", str(target)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (hint,) = [
        line for line in result.stdout.splitlines() if "delete finished patch scripts" in line
    ]
    assert hint.endswith("rm patch_0001_old_one.py patch_0002_old_two.py"), hint
    assert all((target / name).is_file() for name in scripts)  # listed or not, nothing is deleted
