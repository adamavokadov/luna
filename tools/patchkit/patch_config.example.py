"""Example configuration for tools/patchkit/build_patch.py (copy it, edit it, pass --config)."""

PATCH_ID = "0002-example"  # NNNN-slug; the script file is patch_NNNN_slug.py
TITLE = "One-line description of the change"
COMMIT_MESSAGE = "feat: short subject\n\n- what changed\n- why"
DOC = """
patch_0002_example: one-line description.

Usage (from the repository root):
    python3 patch_0002_example.py --dry-run    # show the plan, change nothing
    python3 patch_0002_example.py              # apply
    python3 patch_0002_example.py --verify     # apply, then uv sync + make check
    python3 patch_0002_example.py --rollback   # undo the last application
"""

MOVES: dict[str, str] = {}  # destination -> source, for files that moved (content may also change)
OVERWRITE: set[str] = set()  # existing files that are replaced as a whole (a backup is kept)
APPEND_LINES: set[str] = {".gitignore"}  # ignore-style files: merge only missing entries
IF_MISSING: set[str] = set()  # new files that must never replace an existing one (dotfiles, CI)
