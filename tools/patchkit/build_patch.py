#!/usr/bin/env python3
"""Build a self-contained patch script from the difference between two repository trees.

    python3 tools/patchkit/build_patch.py PRISTINE_DIR WORK_DIR OUT_FILE \
        --config patch_config.py --handoff handoff_entry.md

* PRISTINE_DIR: the repository as the owner has it (e.g. unpacked from the repomix export);
* WORK_DIR:     the same tree after the changes;
* --config:     a Python file with PATCH_ID, TITLE, COMMIT_MESSAGE, DOC, MOVES, OVERWRITE,
                APPEND_LINES, IF_MISSING (see patch_config.example.py);
* --handoff:    Markdown for the HANDOFF.md session-log entry (first line is its heading).

New files become whole blocks, existing files become anchored hunks, moves stay moves.
Stdlib only. See docs/MODUS_OPERANDI.md.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).parent
IGNORE_DIRS = {
    ".venv", ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".patch-backups",
}  # fmt: skip
IGNORE_FILES = {"uv.lock", "repomix-output.xml"}
IGNORE_TOP = {"data"}  # the bot's runtime data directory (top level only)
CONTEXTS = (3, 5, 8, 12, 20, 40, 80)  # lines of context around a change, widened until unique


def load_config(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("patch_config", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load config {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_tree(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if set(rel.parts) & IGNORE_DIRS or rel.parts[0] in IGNORE_TOP or rel.name in IGNORE_FILES:
            continue
        files[rel.as_posix()] = path.read_bytes().decode("utf-8")  # binary files are unsupported
    return files


def make_hunks(old: str, new: str) -> list[tuple[str, str]]:
    """(old, new) snippets, each `old` occurring exactly once in the original text."""
    a = old.splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for context in CONTEXTS:
        result: list[tuple[str, str]] = []
        for group in matcher.get_grouped_opcodes(n=context):
            i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]
            before, after = "".join(a[i1:i2]), "".join(b[j1:j2])
            if not before or old.count(before) != 1:
                break
            result.append((before, after))
        else:
            return result
    return [(old, new)]  # last resort: replace the whole file


def encode_block(key: str, text: str) -> str:
    """Every payload line is a comment, so the generated script stays valid Python."""
    if "\r" in text:
        raise SystemExit(f"block {key} contains a carriage return; use LF line endings")
    body = "\n".join(f"# {line}" if line else "#" for line in text.split("\n"))
    return f"#@@@BLOCK {key}\n{body}\n"


def build(
    pristine_dir: Path, work_dir: Path, out_file: Path, config: ModuleType, handoff: str
) -> dict[str, int]:
    old_tree, new_tree = read_tree(pristine_dir), read_tree(work_dir)
    moves: dict[str, str] = getattr(config, "MOVES", {})  # destination -> source
    blocks: dict[str, str] = {}

    def block(text: str) -> str:
        key = f"b{len(blocks) + 1:04d}"
        blocks[key] = text
        return key

    ops: list[tuple[Any, ...]] = []
    for dst, src in moves.items():
        if src not in old_tree or dst not in new_tree or src in new_tree:
            raise SystemExit(f"inconsistent move {src} -> {dst}")
        ops.append(("move", src, dst))
    if removed := [p for p in old_tree if p not in new_tree and p not in moves.values()]:
        raise SystemExit(f"unexpected deletions (patches do not delete files): {removed}")

    writes: list[tuple[Any, ...]] = []
    appends: list[tuple[Any, ...]] = []
    replaces: list[tuple[Any, ...]] = []
    for path, text in new_tree.items():
        before = old_tree.get(path, old_tree.get(moves.get(path, "")))
        if before == text:
            continue
        if path in getattr(config, "APPEND_LINES", ()):
            appends.append(("append_lines", path, block(text)))
        elif before is None:
            mode = "if_missing" if path in getattr(config, "IF_MISSING", ()) else "create"
            writes.append(("write", path, block(text), mode, None))
        elif path in getattr(config, "OVERWRITE", ()):
            sha = hashlib.sha256(before.encode("utf-8")).hexdigest()
            writes.append(("write", path, block(text), "overwrite", sha))
        else:
            for old, new in make_hunks(before, text):
                replaces.append(("replace", path, block(old), block(new)))

    ops += sorted(writes, key=lambda op: op[1]) + appends + replaces
    ops.append(("handoff", block(handoff.strip() + "\n")))

    engine = (HERE / "engine.py.tmpl").read_text(encoding="utf-8")
    for token, value in {
        "@@DOC@@": config.DOC.strip(),
        "@@PATCH_ID@@": repr(config.PATCH_ID),
        "@@TITLE@@": repr(config.TITLE),
        "@@COMMIT@@": repr(config.COMMIT_MESSAGE),
    }.items():
        engine = engine.replace(token, value)
    placeholder = "OPS: list[tuple[str, ...]] = []  # filled in below by the generator\n"
    if placeholder not in engine:
        raise SystemExit("engine template lost its OPS placeholder")
    engine = engine.replace(
        placeholder, "OPS: list[tuple] = [\n" + "".join(f"    {op!r},\n" for op in ops) + "]\n"
    )

    payload = "".join(encode_block(key, text) for key, text in blocks.items()) + "#@@@END\n"
    script = (
        engine.rstrip("\n")
        + '\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'
        + "\n# ===== PAYLOAD (generated; do not edit below this line) =====\n"
        + payload
    )
    out_file.write_text(script, encoding="utf-8")
    kinds = ("move", "write", "append_lines", "replace", "handoff")
    return {kind: sum(1 for op in ops if op[0] == kind) for kind in kinds}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("pristine", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    args = parser.parse_args()
    summary = build(
        args.pristine,
        args.work,
        args.out,
        load_config(args.config),
        args.handoff.read_text(encoding="utf-8"),
    )
    print(f"built {args.out} ({args.out.stat().st_size // 1024} KiB): {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
